#!/usr/bin/env python3
"""
WP3-C5: Safe YouTube Path Provenance Inspector.

Reads source_posts and source_post_media from Sheets (read-only, dry_run=True),
analyses YouTube path shapes, classifies the provenance of the 3 MIXED_OR_UNRESOLVED rows,
and emits a safe JSON report with no raw URLs, IDs, or secrets.
"""
from __future__ import annotations

import os
import sys
import json
import hashlib
import argparse
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from src.config_loader import get_config
from src.sheets_client import SheetsClient
from src.youtube_path_provenance import analyse_youtube_url, shape_to_safe_dict, TabKind, PathShape
from scripts.inspect_wp3c3_source_identity_collision import (
    TARGET_SOURCE_POST_ID,
    prevent_writes,
    check_safety_flags,
    read_rows_with_sheet_numbers,
    parse_non_negative_integer,
    normalize_media_type,
)

SCHEMA_VERSION = 1
MODE = "READ_ONLY_SAFE_YOUTUBE_PATH_PROVENANCE"
SAFE_OUTPUT_PREFIX = "WP3C5_SAFE_YOUTUBE_PATH_PROVENANCE_JSON="

# Allowed channel-tab kinds for HISTORICAL_CHANNEL_TAB_PSEUDO_ENTRIES classification
_ALLOWED_CHANNEL_TAB_KINDS = {
    TabKind.VIDEOS.value,
    TabKind.SHORTS.value,
    TabKind.STREAMS.value,
    TabKind.LIVE.value,
    TabKind.PLAYLISTS.value,
    TabKind.COMMUNITY.value,
    TabKind.ABOUT.value,
    TabKind.FEATURED.value,
    TabKind.NONE.value,
}

# Account/channel/user root and tab shapes
_ACCOUNT_OR_TAB_SHAPES = {
    PathShape.YOUTUBE_HANDLE_ROOT.value,
    PathShape.YOUTUBE_HANDLE_TAB.value,
    PathShape.YOUTUBE_CHANNEL_ROOT.value,
    PathShape.YOUTUBE_CHANNEL_TAB.value,
    PathShape.YOUTUBE_USER_ROOT.value,
    PathShape.YOUTUBE_USER_TAB.value,
    PathShape.YOUTUBE_CUSTOM_ROOT.value,
    PathShape.YOUTUBE_CUSTOM_TAB.value,
}

_ACQUISITION_METHOD_FAMILIES = {"YT_DLP_RESOLVE_ON_INGEST", "MANUAL", "OTHER", "EMPTY"}


def _safe_hash(val: str) -> str:
    return hashlib.sha256(val.encode("utf-8")).hexdigest()


def _ordinal_group(val: str, registry: dict[str, str], prefix: str) -> str:
    """Map raw value to ordinal group label via SHA-256 registry."""
    h = _safe_hash(val)
    if h not in registry:
        n = len(registry) + 1
        registry[h] = f"{prefix}_{n}"
    return registry[h]


def _acquisition_method_family(raw: str) -> str:
    """Classify acquisition method to safe family label."""
    v = str(raw).strip().upper()
    if not v:
        return "EMPTY"
    for fam in ("YT_DLP_RESOLVE_ON_INGEST", "MANUAL"):
        if fam in v:
            return fam
    return "OTHER"


def _static_trace() -> dict:
    """
    Inspect repo code for provenance signals. No network requests.
    Returns safe bool flags and file-path labels only.
    """
    import ast

    def _path_contains(rel_path: str, needle: str) -> bool:
        full = ROOT / rel_path
        if not full.exists():
            return False
        try:
            return needle in full.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return False

    # source_post_id generation: uses source_id and external_post_id
    # src/acquisition/ytdlp.py: post_id = f"sp_{source['source_id']}_{post_external_id}"
    uses_source_and_external = (
        _path_contains("src/acquisition/ytdlp.py", "source_id") and
        _path_contains("src/acquisition/ytdlp.py", "external_post_id")
    )

    # source_post_media_id generation: uses parent_id and media_index
    uses_parent_and_media_index = (
        _path_contains("src/acquisition/ytdlp.py", "spm_") and
        _path_contains("src/acquisition/tiktok_public.py", "spm_")
    )

    # discovery rejects nonpost YouTube URLs
    rejects_nonpost = _path_contains(
        "src/acquisition/ytdlp.py",
        "/channel/"
    )

    # handles channel landing pages
    handles_channel_landing = _path_contains(
        "src/acquisition/ytdlp.py",
        "/videos"
    )

    # Candidate historical writers (files that write source_posts or source_post_media)
    candidate_files = []
    for rel in [
        "scripts/seed_source_registry.py",
        "scripts/seed_reference_posts_from_sources.py",
        "src/acquisition/ytdlp.py",
        "src/acquisition/tiktok_public.py",
        "src/acquisition/threads_public.py",
        "src/seeds.py",
    ]:
        full = ROOT / rel
        if full.exists():
            text = full.read_text(encoding="utf-8", errors="replace")
            if "source_post_id" in text or "source_post_media_id" in text or "append_row" in text:
                candidate_files.append(rel)

    return {
        "current_parent_id_uses_source_and_external_id": uses_source_and_external,
        "current_child_id_uses_parent_and_media_index": uses_parent_and_media_index,
        "current_discovery_rejects_nonpost_youtube_urls": rejects_nonpost,
        "current_discovery_handles_channel_landing_pages": handles_channel_landing,
        "candidate_historical_writer_count": len(candidate_files),
        "candidate_historical_writer_labels": candidate_files,
    }


def _build_fail_result(status_reasons: list[str], checked_sha: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": MODE,
        "overall_status": "FAIL",
        "classification": "MIXED_OR_UNRESOLVED",
        "status_reasons": status_reasons,
        "checked_commit_sha": checked_sha,
        "counts": {
            "parent_count": 0,
            "child_count": 0,
            "unique_external_post_id_group_count": 0,
            "unique_source_id_group_count": 0,
            "unique_child_id_group_count": 0,
            "unique_parent_canonical_url_group_count": 0,
            "unique_child_canonical_url_group_count": 0,
            "unique_child_original_media_url_group_count": 0,
            "unique_parent_tab_kind_count": 0,
            "unique_child_tab_kind_count": 0,
            "parent_child_url_group_match_count": 0,
            "parent_child_row_number_match_count": 0,
            "unique_parent_recovered_group_count": 0,
            "unique_child_recovered_group_count": 0,
        },
        "static_trace": {
            "current_parent_id_uses_source_and_external_id": False,
            "current_child_id_uses_parent_and_media_index": False,
            "current_discovery_rejects_nonpost_youtube_urls": False,
            "current_discovery_handles_channel_landing_pages": False,
            "candidate_historical_writer_count": 0,
            "candidate_historical_writer_labels": [],
        },
        "parents": [],
        "children": [],
        "recommended_next_action": "MANUAL_INVESTIGATION",
        "apply_operations": [],
    }


def _classify(parents: list[dict], children: list[dict],
               parent_tab_kinds: list[str], child_tab_kinds: list[str]) -> tuple[str, str]:
    """
    Returns (classification, recommended_next_action).
    """
    pc = len(parents)
    cc = len(children)

    all_youtube = all(
        p["host_family"] in ("YOUTUBE", "YOUTU_BE") for p in parents
    ) and all(
        c["host_family"] in ("YOUTUBE", "YOUTU_BE") for c in children
    )

    if not all_youtube:
        return "MIXED_OR_UNRESOLVED", "MANUAL_INVESTIGATION"

    all_no_post_identity = all(
        not p["post_identity_extracted"] for p in parents
    ) and all(
        not c["post_identity_extracted"] for c in children
    )

    all_account_or_tab = all(
        p["path_shape"] in _ACCOUNT_OR_TAB_SHAPES for p in parents
    ) and all(
        c["path_shape"] in _ACCOUNT_OR_TAB_SHAPES for c in children
    )

    # Check HISTORICAL_CHANNEL_TAB_PSEUDO_ENTRIES
    if (
        pc == 3 and cc == 3
        and all_no_post_identity
        and all_account_or_tab
    ):
        unique_tab_kinds = set(parent_tab_kinds) | set(child_tab_kinds)
        all_tabs_allowed = all(tk in _ALLOWED_CHANNEL_TAB_KINDS for tk in unique_tab_kinds)
        unique_tabs_excl_none = unique_tab_kinds - {"NONE"}
        two_or_more_tab_kinds = len(unique_tabs_excl_none) >= 2

        # ordinal group counts
        ext_post_groups = set(p.get("external_post_id_group", "") for p in parents)
        src_groups = set(p.get("source_id_group", "") for p in parents)
        child_id_groups = set(c.get("child_id_group", "") for c in children)

        unique_ext_post_id_count = len(ext_post_groups)
        unique_src_id_count = len(src_groups)
        unique_child_id_count = len(child_id_groups)

        all_child_media_index_zero = all(
            c.get("media_index") == 0 for c in children
        )

        parent_canon_groups = set(p.get("canonical_url_group", "") for p in parents)
        child_canon_groups = set(c.get("canonical_url_group", "") for c in children)
        child_media_url_groups = set(c.get("original_media_url_group", "") for c in children)
        url_groups_match_one_to_one = (
            len(parent_canon_groups) == len(children) and
            parent_canon_groups == child_canon_groups
        )

        unique_parent_sem_count = len(set(p.get("semantic_parent_group", "") for p in parents))

        if (
            all_tabs_allowed
            and two_or_more_tab_kinds
            and unique_ext_post_id_count == 1
            and unique_src_id_count == 1
            and unique_child_id_count == 1
            and all_child_media_index_zero
            and url_groups_match_one_to_one
            and unique_parent_sem_count == 1
            and len(child_media_url_groups) > 1
        ):
            return "HISTORICAL_CHANNEL_TAB_PSEUDO_ENTRIES", "PLAN_HISTORICAL_PSEUDO_ENTRY_REPAIR_REVIEW"

        # Account-page collision but not all conditions met
        return "ACCOUNT_PAGE_COLLISION_CONFIRMED", "TRACE_HISTORICAL_WRITER"

    # All YouTube but not post URL nor account/tab
    all_nonpost_youtube = all_youtube and all(
        p["path_shape"] not in _ACCOUNT_OR_TAB_SHAPES and
        p["path_shape"] != PathShape.YOUTUBE_POST_URL.value
        for p in parents
    ) and all(
        c["path_shape"] not in _ACCOUNT_OR_TAB_SHAPES and
        c["path_shape"] != PathShape.YOUTUBE_POST_URL.value
        for c in children
    )
    if all_nonpost_youtube:
        return "NONPOST_YOUTUBE_URL_COLLISION", "TRACE_DATA_ORIGIN"

    return "MIXED_OR_UNRESOLVED", "MANUAL_INVESTIGATION"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output_path = args.output

    checked_sha = str(os.environ.get("GITHUB_SHA", "0" * 40)).strip()[:64]

    # Stage 1: Safety flag check
    if check_safety_flags():
        result = _build_fail_result(["UNSAFE_FLAG_ENABLED"], checked_sha)
        result["overall_status"] = "FAIL"
        _emit_and_exit(result, output_path, 1)
        return

    # Stage 2: Client initialisation
    try:
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
        prevent_writes(client)
    except Exception:
        result = _build_fail_result(["CLIENT_INITIALIZATION_FAILED"], checked_sha)
        _emit_and_exit(result, output_path, 1)
        return

    # Stage 3: Worksheet read
    try:
        ws_posts = client._ws("source_posts")
        ws_media = client._ws("source_post_media")
        prevent_writes(ws_posts)
        prevent_writes(ws_media)
        source_posts_rows = read_rows_with_sheet_numbers(ws_posts)
        source_post_media_rows = read_rows_with_sheet_numbers(ws_media)
    except Exception:
        result = _build_fail_result(["WORKSHEET_READ_FAILED"], checked_sha)
        _emit_and_exit(result, output_path, 1)
        return

    # Stage 4: Analysis
    try:
        result = _analyse(
            source_posts_rows, source_post_media_rows, checked_sha
        )
    except Exception:
        result = _build_fail_result(["ANALYSIS_FAILED"], checked_sha)
        _emit_and_exit(result, output_path, 1)
        return

    _emit_and_exit(result, output_path, 0)


def _emit_and_exit(result: dict, output_path: str, code: int) -> None:
    safe_str = json.dumps(result, ensure_ascii=False)
    print(f"{SAFE_OUTPUT_PREFIX}{safe_str}")
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(safe_str)
    except Exception:
        pass
    sys.exit(code)


def _analyse(
    source_posts_rows: list[tuple[int, dict]],
    source_post_media_rows: list[tuple[int, dict]],
    checked_sha: str,
) -> dict:
    # Filter for target
    parents_raw = [
        (rn, row) for rn, row in source_posts_rows
        if str(row.get("source_post_id", "")).strip() == TARGET_SOURCE_POST_ID
    ]
    children_raw = [
        (rn, row) for rn, row in source_post_media_rows
        if str(row.get("source_post_id", "")).strip() == TARGET_SOURCE_POST_ID
    ]

    # Ordinal group registries (hash -> label)
    ext_post_id_reg: dict[str, str] = {}
    source_id_reg: dict[str, str] = {}
    parent_canon_url_reg: dict[str, str] = {}
    child_canon_url_reg: dict[str, str] = {}
    child_id_reg: dict[str, str] = {}
    media_url_reg: dict[str, str] = {}
    disc_at_reg: dict[str, str] = {}
    created_at_reg: dict[str, str] = {}
    parent_sem_reg: dict[str, str] = {}
    child_sem_reg: dict[str, str] = {}

    parent_tab_kinds: list[str] = []
    parent_dicts: list[dict] = []

    for candidate_number, (sheet_row_number, row) in enumerate(parents_raw, start=1):
        canon_url = str(row.get("canonical_post_url", "")).strip()
        ext_id = str(row.get("external_post_id", "")).strip()
        source_id = str(row.get("source_id", "")).strip()
        source_acc_id = str(row.get("source_account_id", "")).strip()
        disc_at = str(row.get("discovered_at", "")).strip()
        created_at = str(row.get("created_at", "")).strip()
        dmc_val = parse_non_negative_integer(row.get("media_count", ""))
        media_count = dmc_val if dmc_val is not None else 0

        shape = analyse_youtube_url(canon_url)
        shape_dict = shape_to_safe_dict(shape)

        canon_group = _ordinal_group(canon_url, parent_canon_url_reg, "PARENT_CANON_URL_GROUP")
        ext_post_group = _ordinal_group(ext_id if ext_id else f"__empty_parent_{candidate_number}", ext_post_id_reg, "EXT_POST_ID_GROUP")
        src_group = _ordinal_group(source_id if source_id else f"__empty_src_{candidate_number}", source_id_reg, "SOURCE_ID_GROUP")
        src_acc_group = _ordinal_group(source_acc_id if source_acc_id else f"__empty_acc_{candidate_number}", source_id_reg, "SOURCE_ACC_ID_GROUP")
        disc_group = _ordinal_group(disc_at, disc_at_reg, "DISC_AT_GROUP")
        created_group = _ordinal_group(created_at, created_at_reg, "CREATED_AT_GROUP")

        # Semantic parent group: path_shape + tab_kind + host_family + source_id_group + media_count
        sem_key = f"{shape.path_shape.value}|{shape.tab_kind.value}|{shape.host_family}|{src_group}|{media_count}"
        sem_group = _ordinal_group(sem_key, parent_sem_reg, "SEM_PARENT_GROUP")

        parent_tab_kinds.append(shape.tab_kind.value)

        parent_dicts.append({
            "candidate_number": candidate_number,
            "sheet_row_number": sheet_row_number,
            "external_post_id_group": ext_post_group,
            "source_id_group": src_group,
            "source_account_id_group": src_acc_group,
            "canonical_url_group": canon_group,
            "discovered_at_group": disc_group,
            "created_at_group": created_group,
            "semantic_parent_group": sem_group,
            "path_shape": shape.path_shape.value,
            "tab_kind": shape.tab_kind.value,
            "post_kind": shape.post_kind.value,
            "media_count": media_count,
            **shape_dict,
        })

    child_tab_kinds: list[str] = []
    child_dicts: list[dict] = []

    for child_number, (sheet_row_number, row) in enumerate(children_raw, start=1):
        canon_url = str(row.get("canonical_post_url", "")).strip()
        media_url = str(row.get("original_media_url", "")).strip()
        child_id = str(row.get("source_post_media_id", "")).strip()
        created_at = str(row.get("created_at", "")).strip()
        mi_val = parse_non_negative_integer(row.get("media_index", ""))
        media_index = mi_val if mi_val is not None else 0
        media_type = normalize_media_type(row.get("media_type"))
        acq_raw = str(row.get("acquisition_method", row.get("ingestion_method", ""))).strip()
        acq_family = _acquisition_method_family(acq_raw)

        shape = analyse_youtube_url(canon_url)
        shape_dict = shape_to_safe_dict(shape)

        canon_group = _ordinal_group(canon_url, child_canon_url_reg, "CHILD_CANON_URL_GROUP")
        media_url_group = _ordinal_group(media_url if media_url else f"__empty_media_{child_number}", media_url_reg, "MEDIA_URL_GROUP")
        child_id_group = _ordinal_group(child_id if child_id else f"__empty_child_id_{child_number}", child_id_reg, "CHILD_ID_GROUP")
        created_group = _ordinal_group(created_at, created_at_reg, "CREATED_AT_GROUP")

        sem_key = f"{shape.path_shape.value}|{shape.tab_kind.value}|{shape.host_family}|{child_id_group}|{media_index}|{media_type}"
        sem_group = _ordinal_group(sem_key, child_sem_reg, "SEM_CHILD_GROUP")

        child_tab_kinds.append(shape.tab_kind.value)

        child_dicts.append({
            "child_number": child_number,
            "sheet_row_number": sheet_row_number,
            "child_id_group": child_id_group,
            "canonical_url_group": canon_group,
            "original_media_url_group": media_url_group,
            "created_at_group": created_group,
            "semantic_child_group": sem_group,
            "path_shape": shape.path_shape.value,
            "tab_kind": shape.tab_kind.value,
            "post_kind": shape.post_kind.value,
            "media_index": media_index,
            "media_type": media_type,
            "acquisition_method_family": acq_family,
            **shape_dict,
        })

    classification, recommended_next_action = _classify(
        parent_dicts, child_dicts, parent_tab_kinds, child_tab_kinds
    )

    # Counts
    parent_canon_groups = set(p["canonical_url_group"] for p in parent_dicts)
    child_canon_groups = set(c["canonical_url_group"] for c in child_dicts)
    url_match_count = len(parent_canon_groups & child_canon_groups)
    parent_rows = set(p["sheet_row_number"] for p in parent_dicts)
    child_rows = set(c["sheet_row_number"] for c in child_dicts)
    row_match_count = len(parent_rows & child_rows)

    unique_ext_post_id_count = len(set(p["external_post_id_group"] for p in parent_dicts))
    unique_src_id_count = len(set(p["source_id_group"] for p in parent_dicts))
    unique_child_id_count = len(set(c["child_id_group"] for c in child_dicts))
    unique_parent_canon_count = len(parent_canon_groups)
    unique_child_canon_count = len(child_canon_groups)
    unique_media_url_count = len(set(c["original_media_url_group"] for c in child_dicts))
    unique_parent_tab_kind_count = len(set(parent_tab_kinds))
    unique_child_tab_kind_count = len(set(child_tab_kinds))

    # Status
    status_reasons = [classification] if classification != "MIXED_OR_UNRESOLVED" else ["MIXED_OR_UNRESOLVED"]
    if not parent_dicts:
        status_reasons = ["NO_PARENT_ROWS"]
    if not child_dicts:
        status_reasons = status_reasons + ["NO_CHILD_ROWS"] if status_reasons != ["NO_PARENT_ROWS"] else ["NO_PARENT_ROWS", "NO_CHILD_ROWS"]

    static_trace_result = _static_trace()

    return {
        "schema_version": SCHEMA_VERSION,
        "mode": MODE,
        "overall_status": "READY_FOR_MANUAL_DECISION",
        "classification": classification,
        "status_reasons": status_reasons,
        "checked_commit_sha": checked_sha,
        "counts": {
            "parent_count": len(parent_dicts),
            "child_count": len(child_dicts),
            "unique_external_post_id_group_count": unique_ext_post_id_count,
            "unique_source_id_group_count": unique_src_id_count,
            "unique_child_id_group_count": unique_child_id_count,
            "unique_parent_canonical_url_group_count": unique_parent_canon_count,
            "unique_child_canonical_url_group_count": unique_child_canon_count,
            "unique_child_original_media_url_group_count": unique_media_url_count,
            "unique_parent_tab_kind_count": unique_parent_tab_kind_count,
            "unique_child_tab_kind_count": unique_child_tab_kind_count,
            "parent_child_url_group_match_count": url_match_count,
            "parent_child_row_number_match_count": row_match_count,
            "unique_parent_recovered_group_count": 0,
            "unique_child_recovered_group_count": 0,
        },
        "static_trace": static_trace_result,
        "parents": parent_dicts,
        "children": child_dicts,
        "recommended_next_action": recommended_next_action,
        "apply_operations": [],
    }


if __name__ == "__main__":
    main()
