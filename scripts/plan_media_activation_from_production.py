#!/usr/bin/env python3
"""Build a read-only activation plan from existing Production media records."""

from __future__ import annotations

import argparse
import json
import os
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

ACCOUNTS = ("night_scout", "liver_manager")
ROUTES = ("direct_reference_media", "approved_source_clip")
DANGEROUS_ENV = (
    "PUBLISH_ENABLED",
    "ALLOW_REAL_X_POST",
    "ALLOW_REAL_THREADS_POST",
    "ALLOW_MEDIA_POSTS",
    "ALLOW_REAL_THREADS_VIDEO_POST",
    "ALLOW_VIDEO_DOWNLOAD",
    "ALLOW_VIDEO_CUT",
    "ALLOW_CLOUDINARY_UPLOAD",
    "ALLOW_TRANSCRIPTION_API",
    "GITHUB_MODELS_ENABLED",
    "ENABLE_SENTENCE_TRANSFORMERS",
)
EVIDENCE_FIELDS = (
    "public_post_text",
    "validator_status",
    "internal_leak_status",
    "account_fit_status",
    "caption_provider",
    "caption_provider_version",
    "alignment_status",
    "final_alignment_score",
    "main_claim_coverage",
    "unsupported_claim_count",
    "source_copy_similarity",
    "recent_post_similarity",
    "claim_support_json",
    "content_hash",
    "batch_id",
    "batch_diversity_status",
    "batch_similarity_score",
    "primary_topic",
    "supporting_topics",
    "topic_confidence",
    "topic_coherence_status",
    "topic_coherence_score",
    "structure_variant",
    "hook_topic_match",
    "closing_topic_match",
    "quality_gate_version",
    "feature_schema_version",
    "media_primary_topic",
    "visual_topic",
    "visual_topic_match",
    "visual_cta_match",
    "visual_plan_version",
    "visual_text_hash",
    "generation_attempt",
    "generation_rule_version",
    "generation_policy_json",
)

PermissionChecker = Callable[..., bool]
Planner = Callable[[list[dict[str, Any]]], dict[str, Any]]
CandidateValidator = Callable[[dict[str, Any]], list[str]]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _true(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes"}


def safety_blockers(environ: Mapping[str, str] | None = None) -> list[str]:
    source = os.environ if environ is None else environ
    return [f"{name}=true" for name in DANGEROUS_ENV if _true(source.get(name))]


def _account_id(row: Mapping[str, Any]) -> str:
    return _text(row.get("account_id") or row.get("target_account_id"))


def _canonical_route(row: Mapping[str, Any]) -> str:
    values = (
        row.get("content_route"),
        row.get("content_type"),
        row.get("generation_mode"),
    )
    aliases = {
        "direct_reference_media": "direct_reference_media",
        "saved_direct_reference_media": "direct_reference_media",
        "direct_image": "direct_reference_media",
        "direct_video": "direct_reference_media",
        "direct_carousel": "direct_reference_media",
        "approved_source_clip": "approved_source_clip",
        "saved_approved_source_clip": "approved_source_clip",
        "approved_saved_media": "approved_source_clip",
    }
    for value in values:
        route = aliases.get(_text(value).lower(), "")
        if route:
            return route
    return ""


def _evidence_score(row: Mapping[str, Any]) -> tuple[int, str, str]:
    populated = sum(1 for field in EVIDENCE_FIELDS if _text(row.get(field)))
    passes = sum(
        1
        for field in (
            "validator_status",
            "internal_leak_status",
            "account_fit_status",
            "alignment_status",
            "batch_diversity_status",
            "topic_coherence_status",
        )
        if _text(row.get(field)).upper() == "PASS"
    )
    timestamp = _text(row.get("updated_at") or row.get("created_at"))
    queue_id = _text(row.get("queue_id"))
    return populated + (passes * 3), timestamp, queue_id


def _queue_evidence_allowed(row: Mapping[str, Any]) -> bool:
    status = _text(row.get("status")).upper()
    if status in {"POSTED", "LEGACY_INVALID_CANARY", "DELETED"}:
        return False
    if _true(row.get("excluded_from_activation")):
        return False
    if _true(row.get("repost_prohibited")):
        return False
    if _text(row.get("posted_at")) or _text(row.get("result_id")):
        return False
    return True


def _linked_value(row: Mapping[str, Any], link_field: str) -> str:
    if link_field == "clip_candidate_id":
        return _text(row.get("clip_candidate_id") or row.get("video_clip_id"))
    return _text(row.get(link_field))


def best_queue_evidence(
    queue_rows: list[dict[str, Any]],
    *,
    account_id: str,
    route: str,
    link_field: str,
    link_value: str,
) -> dict[str, Any]:
    candidates = [
        dict(row)
        for row in queue_rows
        if _queue_evidence_allowed(row)
        and _account_id(row) == account_id
        and _canonical_route(row) == route
        and _linked_value(row, link_field) == link_value
    ]
    if not candidates:
        return {}
    candidates.sort(key=_evidence_score, reverse=True)
    return candidates[0]


def _active_permission(
    permissions: list[dict[str, Any]],
    *,
    account_id: str,
    source_id: str,
    operation: str,
    permission_checker: PermissionChecker,
) -> dict[str, Any]:
    candidates = [
        dict(row)
        for row in permissions
        if _text(row.get("source_id")) == source_id
        and permission_checker(row, account_id=account_id, operation=operation)
    ]
    candidates.sort(
        key=lambda row: (
            _text(row.get("updated_at") or row.get("created_at")),
            _text(row.get("permission_id")),
        ),
        reverse=True,
    )
    return candidates[0] if candidates else {}



def select_permissioned_direct_candidate(
    candidates: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]],
    *,
    permissions: list[dict[str, Any]],
    account_id: str,
    permission_checker: PermissionChecker,
) -> tuple[
    tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None,
    list[str],
]:
    """Return the first direct candidate backed by the active permission ledger."""

    rejected: list[str] = []

    for selection in candidates:
        post, _media, source = selection
        source_id = _text(post.get("source_id") or source.get("source_id"))
        permission = _active_permission(
            permissions,
            account_id=account_id,
            source_id=source_id,
            operation="direct",
            permission_checker=permission_checker,
        )

        if permission:
            return selection, rejected

        rejected.append(
            f"{_text(post.get('source_post_id'))}:"
            "active_direct_permission_missing"
        )

    return None, rejected


def _media_bundle(primary: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = primary.get("carousel_media")
    if isinstance(raw, list) and raw:
        return [dict(item) for item in raw if isinstance(item, dict)]
    return [dict(primary)]


def _media_identity(row: Mapping[str, Any]) -> str:
    return _text(
        row.get("media_asset_id")
        or row.get("media_id")
        or row.get("source_post_media_id")
    )


def _media_url(row: Mapping[str, Any]) -> str:
    return _text(row.get("storage_url") or row.get("cloudinary_url"))


def _publisher_media_type(media_types: list[str]) -> str:
    normalized = [value.lower() for value in media_types if value]
    if len(normalized) > 1:
        return "CAROUSEL"
    if normalized and normalized[0] == "image":
        return "IMAGE"
    return "VIDEO"


def _copy_evidence(*rows: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for row in rows:
        for field in EVIDENCE_FIELDS:
            value = row.get(field)
            if _text(value):
                result[field] = value
        if not _text(result.get("validator_status")):
            validator = row.get("public_post_validator_status")
            if _text(validator):
                result["validator_status"] = validator
    return result


def _direct_candidate(
    *,
    account_id: str,
    selection: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
    queue_rows: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    permission_checker: PermissionChecker,
) -> tuple[dict[str, Any], dict[str, Any]]:
    post, primary_media, source = (dict(item) for item in selection)
    source_post_id = _text(post.get("source_post_id"))
    source_id = _text(post.get("source_id") or source.get("source_id"))
    permission = _active_permission(
        permissions,
        account_id=account_id,
        source_id=source_id,
        operation="direct",
        permission_checker=permission_checker,
    )
    evidence = best_queue_evidence(
        queue_rows,
        account_id=account_id,
        route="direct_reference_media",
        link_field="source_post_id",
        link_value=source_post_id,
    )
    bundle = _media_bundle(primary_media)
    asset_ids = [_media_identity(item) for item in bundle]
    urls = [_media_url(item) for item in bundle]
    media_types = [_text(item.get("media_type")).lower() for item in bundle]
    candidate = _copy_evidence(post, source, evidence)
    candidate.update(
        {
            "account_id": account_id,
            "content_route": "direct_reference_media",
            "source_id": source_id,
            "source_post_id": source_post_id,
            "source_url": _text(post.get("canonical_post_url") or post.get("post_url")),
            "permission_id": _text(permission.get("permission_id")),
            "permission_evidence": _text(permission.get("evidence_reference")),
            "rights_status": _text(permission.get("rights_status")),
            "permission_status": _text(permission.get("permission_status")),
            "media_asset_id": asset_ids[0] if asset_ids else "",
            "media_url": urls[0] if urls else "",
            "media_asset_ids_json": json.dumps(asset_ids, ensure_ascii=False),
            "media_urls_json": json.dumps(urls, ensure_ascii=False),
            "media_types_json": json.dumps(media_types, ensure_ascii=False),
            "media_type": media_types[0] if media_types else "",
            "publisher_media_type": _publisher_media_type(media_types),
            "media_origin": "direct_reference",
            "duration_seconds": primary_media.get("duration_seconds", ""),
            "aspect_ratio": primary_media.get("aspect_ratio", ""),
        }
    )
    return candidate, {
        "source_post_id": source_post_id,
        "source_id": source_id,
        "permission_id": _text(permission.get("permission_id")),
        "evidence_queue_id": _text(evidence.get("queue_id")),
        "media_asset_count": len(asset_ids),
    }


def _clip_candidate(
    *,
    account_id: str,
    selection: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
    queue_rows: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    permission_checker: PermissionChecker,
) -> tuple[dict[str, Any], dict[str, Any]]:
    clip, source_video, asset = (dict(item) for item in selection)
    clip_id = _text(clip.get("clip_candidate_id") or clip.get("clip_id"))
    source_video_id = _text(source_video.get("source_video_id") or clip.get("source_video_id"))
    source_id = _text(source_video.get("source_id") or clip.get("source_id"))
    permission = _active_permission(
        permissions,
        account_id=account_id,
        source_id=source_id,
        operation="clip",
        permission_checker=permission_checker,
    )
    evidence = best_queue_evidence(
        queue_rows,
        account_id=account_id,
        route="approved_source_clip",
        link_field="clip_candidate_id",
        link_value=clip_id,
    )
    media_id = _media_identity(asset)
    media_url = _media_url(asset)
    candidate = _copy_evidence(source_video, clip, evidence)
    candidate.update(
        {
            "account_id": account_id,
            "content_route": "approved_source_clip",
            "source_id": source_id,
            "source_video_id": source_video_id,
            "clip_candidate_id": clip_id,
            "source_video_url": _text(
                source_video.get("canonical_video_url")
                or source_video.get("source_video_url")
            ),
            "start_seconds": _text(clip.get("start_seconds") or clip.get("start_time")),
            "end_seconds": _text(clip.get("end_seconds") or clip.get("end_time")),
            "permission_id": _text(permission.get("permission_id")),
            "permission_evidence": _text(permission.get("evidence_reference")),
            "rights_status": _text(permission.get("rights_status")),
            "permission_status": _text(permission.get("permission_status")),
            "media_asset_id": media_id,
            "media_url": media_url,
            "media_type": "video",
            "publisher_media_type": "VIDEO",
            "media_origin": "approved_source_clip",
            "duration_seconds": asset.get("duration_seconds") or asset.get("duration", ""),
            "aspect_ratio": asset.get("aspect_ratio", ""),
            "width": asset.get("width", ""),
            "height": asset.get("height", ""),
            "video_stream_count": asset.get("video_stream_count", ""),
            "audio_stream_count": asset.get("audio_stream_count", ""),
            "media_probe_status": asset.get("media_probe_status", ""),
            "enforce_video_stream_evidence": "true",
        }
    )
    return candidate, {
        "clip_candidate_id": clip_id,
        "source_video_id": source_video_id,
        "source_id": source_id,
        "permission_id": _text(permission.get("permission_id")),
        "evidence_queue_id": _text(evidence.get("queue_id")),
        "media_asset_id": media_id,
    }


def build_production_plan(
    *,
    direct_selections: Mapping[
        str,
        tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None,
    ],
    clip_selections: Mapping[
        str,
        tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None,
    ],
    queue_rows: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    permission_checker: PermissionChecker,
    planner: Planner,
    candidate_validator: CandidateValidator | None = None,
    selection_diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    selected: dict[str, dict[str, Any]] = {}
    missing: list[str] = []

    for account_id in ACCOUNTS:
        selected[account_id] = {}
        direct = direct_selections.get(account_id)
        if direct is None:
            missing.append(f"{account_id}:direct_reference_media")
        else:
            candidate, summary = _direct_candidate(
                account_id=account_id,
                selection=direct,
                queue_rows=queue_rows,
                permissions=permissions,
                permission_checker=permission_checker,
            )
            candidates.append(candidate)
            selected[account_id]["direct_reference_media"] = summary

        clip = clip_selections.get(account_id)
        if clip is None:
            missing.append(f"{account_id}:approved_source_clip")
        else:
            candidate, summary = _clip_candidate(
                account_id=account_id,
                selection=clip,
                queue_rows=queue_rows,
                permissions=permissions,
                permission_checker=permission_checker,
            )
            candidates.append(candidate)
            selected[account_id]["approved_source_clip"] = summary

    candidate_diagnostics = []
    if candidate_validator is not None:
        for candidate in candidates:
            candidate_diagnostics.append(
                {
                    "account_id": _text(candidate.get("account_id")),
                    "content_route": _text(candidate.get("content_route")),
                    "source_post_id": _text(candidate.get("source_post_id")),
                    "clip_candidate_id": _text(candidate.get("clip_candidate_id")),
                    "blockers": candidate_validator(deepcopy(candidate)),
                }
            )

    activation = planner(deepcopy(candidates))
    return {
        "status": "READ_ONLY_COMPLETE",
        "source_selection_status": "PASS" if not missing else "BLOCKED",
        "activation_plan_status": _text(activation.get("status")) or "BLOCKED",
        "candidate_count": len(candidates),
        "missing_source_slots": missing,
        "selected": selected,
        "selection_diagnostics": dict(selection_diagnostics or {}),
        "candidate_diagnostics": candidate_diagnostics,
        "candidates": candidates,
        "activation_plan": activation,
        "safety": {
            "production_write": False,
            "caption_generation": False,
            "media_download": False,
            "media_cut": False,
            "media_upload": False,
            "queue_write": False,
            "ready_transition": False,
            "workflow_dispatch": False,
            "sns_post": False,
        },
    }


def _read_records(client: Any, logical: str) -> list[dict[str, Any]]:
    from sheets_client import TAB_DEFINITIONS
    from sheets_record_reader import read_records_safely

    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    return [dict(row) for row in read_records_safely(client, logical)]


def load_production_plan() -> dict[str, Any]:
    from config_loader import get_config
    from final_production_contracts import is_active_permission
    from prepare_media_activation_candidates import build_plan, candidate_blockers
    from run_direct_reference_media_pipeline import select_direct_candidates
    from run_media_production_pipeline import select_saved_media_candidate
    from sheets_client import SheetsClient

    config = get_config()
    client = SheetsClient(config["sheet_id"], config["sa_dict"], dry_run=True)
    datasets = {
        logical: _read_records(client, logical)
        for logical in (
            "queue",
            "media_permissions",
            "video_clip_candidates",
            "source_videos",
            "media_assets",
            "posted_results",
        )
    }
    direct_selections: dict[
        str,
        tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None,
    ] = {}
    clip_selections: dict[
        str,
        tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None,
    ] = {}
    diagnostics: dict[str, Any] = {}

    for account_id in ACCOUNTS:
        direct_candidates, direct_reasons = select_direct_candidates(client, account_id)
        direct_selection, direct_permission_reasons = select_permissioned_direct_candidate(
            direct_candidates,
            permissions=datasets["media_permissions"],
            account_id=account_id,
            permission_checker=is_active_permission,
        )
        direct_selections[account_id] = direct_selection
        clip, source_video, asset, clip_reasons = select_saved_media_candidate(
            datasets["video_clip_candidates"],
            datasets["source_videos"],
            datasets["media_assets"],
            datasets["posted_results"],
            account_id,
        )
        clip_selections[account_id] = (
            (clip, source_video, asset)
            if clip is not None and source_video is not None and asset is not None
            else None
        )
        diagnostics[account_id] = {
            "direct_candidate_count": len(direct_candidates),
            "direct_permissioned_candidate_selected": direct_selection is not None,
            "direct_permission_blocked_reasons": direct_permission_reasons[:30],
            "direct_blocked_reasons": (
                direct_permission_reasons + direct_reasons
            )[:30],
            "saved_clip_selected": clip_selections[account_id] is not None,
            "clip_blocked_reasons": clip_reasons[:30],
        }

    return build_production_plan(
        direct_selections=direct_selections,
        clip_selections=clip_selections,
        queue_rows=datasets["queue"],
        permissions=datasets["media_permissions"],
        permission_checker=is_active_permission,
        planner=build_plan,
        candidate_validator=candidate_blockers,
        selection_diagnostics=diagnostics,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    unsafe = safety_blockers()
    if unsafe:
        print(json.dumps({"status": "BLOCKED_UNSAFE_ENV", "blocked_reasons": unsafe}))
        return 1
    if not args.use_sheets:
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["--use-sheets is required"]}))
        return 1

    report = load_production_plan()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=== MEDIA ACTIVATION PRODUCTION PLAN ===")
    print(f"READ_STATUS={report['status']}")
    print(f"SOURCE_SELECTION_STATUS={report['source_selection_status']}")
    print(f"ACTIVATION_PLAN_STATUS={report['activation_plan_status']}")
    print(f"CANDIDATE_COUNT={report['candidate_count']}")
    for account_id in ACCOUNTS:
        routes = report["selected"].get(account_id, {})
        direct = routes.get("direct_reference_media", {})
        clip = routes.get("approved_source_clip", {})
        print(
            f"DIRECT:{account_id}:source_post_id={direct.get('source_post_id', '')}:"
            f"permission={direct.get('permission_id', '')}:"
            f"evidence_queue={direct.get('evidence_queue_id', '')}:"
            f"media_count={direct.get('media_asset_count', 0)}"
        )
        print(
            f"CLIP:{account_id}:clip_candidate_id={clip.get('clip_candidate_id', '')}:"
            f"permission={clip.get('permission_id', '')}:"
            f"evidence_queue={clip.get('evidence_queue_id', '')}:"
            f"media_asset_id={clip.get('media_asset_id', '')}"
        )
    for diagnostic in report.get("candidate_diagnostics", []):
        blockers = diagnostic.get("blockers", [])
        print(
            "CANDIDATE_BLOCKERS:"
            f"{diagnostic.get('account_id', '')}:"
            f"{diagnostic.get('content_route', '')}:"
            + ("|".join(blockers) if blockers else "NONE")
        )
    for failure in report["activation_plan"].get("failures", []):
        print(
            "BLOCKERS:"
            f"{failure.get('account_id', '')}:"
            f"{failure.get('content_route', '')}:"
            + "|".join(failure.get("blockers", []))
        )
    print(f"MISSING_SOURCE_SLOTS={','.join(report['missing_source_slots'])}")
    print(f"REPORT={args.output}")
    print("PASS: read-only Production selection")
    print("PASS: no generation, write, media processing, workflow dispatch or post")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
