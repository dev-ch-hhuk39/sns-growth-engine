#!/usr/bin/env python3
"""Audit whether selected media activation candidates have reusable quality evidence.

The command is read-only. It never generates captions, mutates Sheets, creates
queue rows, changes candidate status, processes media, dispatches workflows, or
posts to an SNS. Existing evidence is considered joinable only when candidate
identity and the public-post hash match exactly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

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
ALIGNMENT_FIELDS = (
    "alignment_status",
    "final_alignment_score",
    "main_claim_coverage",
    "unsupported_claim_count",
    "source_copy_similarity",
    "recent_post_similarity",
    "claim_support_json",
)
PUBLIC_VALIDATION_FIELDS = (
    "validator_status",
    "internal_leak_status",
    "account_fit_status",
)
DESIGN_FIELDS = (
    "batch_id",
    "batch_diversity_status",
    "primary_topic",
    "topic_confidence",
    "topic_coherence_status",
    "structure_variant",
    "hook_topic_match",
    "closing_topic_match",
    "quality_gate_version",
    "feature_schema_version",
)
VISUAL_FIELDS = (
    "media_primary_topic",
    "visual_topic",
    "visual_topic_match",
    "visual_cta_match",
    "visual_plan_version",
    "visual_text_hash",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _true(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes"}


def safety_blockers(environ: Mapping[str, str] | None = None) -> list[str]:
    source = os.environ if environ is None else environ
    return [f"{name}=true" for name in DANGEROUS_ENV if _true(source.get(name))]


def _timestamp(row: Mapping[str, Any]) -> tuple[str, str]:
    return (
        _text(row.get("updated_at") or row.get("created_at")),
        _text(row.get("alignment_id") or row.get("understanding_id")),
    )


def _latest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    return sorted((dict(row) for row in rows), key=_timestamp, reverse=True)[0]


def _public_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def _missing_fields(row: Mapping[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [field for field in fields if not _text(row.get(field))]


def _slot_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return _text(row.get("account_id")), _text(row.get("content_route"))


def _diagnostic_map(plan: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in plan.get("candidate_diagnostics", []):
        if not isinstance(row, Mapping):
            continue
        result[_slot_key(row)] = dict(row)
    return result


def _candidate_map(plan: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for row in plan.get("candidates", []):
        if not isinstance(row, Mapping):
            continue
        result[_slot_key(row)] = dict(row)
    return result


def _selection_reasons(
    plan: Mapping[str, Any],
    *,
    account_id: str,
    route: str,
) -> list[str]:
    diagnostics = plan.get("selection_diagnostics", {})
    account = diagnostics.get(account_id, {}) if isinstance(diagnostics, Mapping) else {}
    if not isinstance(account, Mapping):
        return []
    key = "direct_blocked_reasons" if route == "direct_reference_media" else "clip_blocked_reasons"
    values = account.get(key, [])
    return [str(value) for value in values] if isinstance(values, list) else []


def _semantic_matches(
    rows: list[dict[str, Any]],
    *,
    candidate: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    account_id, route = _slot_key(candidate)
    matching_account = [
        dict(row)
        for row in rows
        if _text(row.get("account_id")) == account_id
    ]
    if route == "direct_reference_media":
        source_post_id = _text(candidate.get("source_post_id"))
        exact = [
            row
            for row in matching_account
            if source_post_id and _text(row.get("source_post_id")) == source_post_id
        ]
        return (_latest(exact), "EXACT_SOURCE_POST") if exact else ({}, "NONE")

    clip_id = _text(candidate.get("clip_candidate_id"))
    exact_clip = [
        row
        for row in matching_account
        if clip_id and _text(row.get("clip_candidate_id")) == clip_id
    ]
    if exact_clip:
        return _latest(exact_clip), "EXACT_CLIP"
    source_video_id = _text(candidate.get("source_video_id"))
    parent = [
        row
        for row in matching_account
        if source_video_id and _text(row.get("source_video_id")) == source_video_id
    ]
    return (_latest(parent), "PARENT_VIDEO_ONLY") if parent else ({}, "NONE")


def _understanding_match(
    rows: list[dict[str, Any]],
    *,
    candidate: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    account_id, route = _slot_key(candidate)
    matching_account = [
        dict(row)
        for row in rows
        if _text(row.get("account_id")) == account_id
    ]
    if route == "direct_reference_media":
        source_post_id = _text(candidate.get("source_post_id"))
        exact = [
            row
            for row in matching_account
            if source_post_id and _text(row.get("source_post_id")) == source_post_id
        ]
        return (_latest(exact), "EXACT_SOURCE_POST") if exact else ({}, "NONE")
    source_video_id = _text(candidate.get("source_video_id"))
    parent = [
        row
        for row in matching_account
        if source_video_id and _text(row.get("source_video_id")) == source_video_id
    ]
    return (_latest(parent), "PARENT_VIDEO") if parent else ({}, "NONE")


def _alignment_recovery(
    candidate: Mapping[str, Any],
    semantic: Mapping[str, Any],
    match_type: str,
) -> dict[str, Any]:
    public_text = _text(candidate.get("public_post_text"))
    expected_hash = _public_hash(public_text)
    stored_hash = _text(semantic.get("public_post_hash"))
    hash_status = (
        "NO_PUBLIC_TEXT"
        if not public_text
        else "MISSING"
        if not stored_hash
        else "MATCH"
        if stored_hash == expected_hash
        else "MISMATCH"
    )
    exact_identity = match_type in {"EXACT_SOURCE_POST", "EXACT_CLIP"}
    alignment_complete = (
        _text(semantic.get("status")).upper() == "PASS"
        and not _missing_fields(semantic, ALIGNMENT_FIELDS[1:])
    )
    joinable = bool(
        exact_identity
        and alignment_complete
        and hash_status == "MATCH"
    )
    recoverable = [
        field
        for field in ALIGNMENT_FIELDS
        if not _text(candidate.get(field)) and _text(semantic.get(field if field != "alignment_status" else "status"))
    ]
    return {
        "match_type": match_type,
        "alignment_id": _text(semantic.get("alignment_id")),
        "status": _text(semantic.get("status")) or "MISSING",
        "public_post_hash_status": hash_status,
        "joinable": joinable,
        "recoverable_fields": recoverable,
        "blocked_reason": (
            ""
            if joinable
            else "public_post_text_missing"
            if hash_status == "NO_PUBLIC_TEXT"
            else "public_post_hash_missing"
            if hash_status == "MISSING"
            else "public_post_hash_mismatch"
            if hash_status == "MISMATCH"
            else "semantic_identity_not_exact"
            if not exact_identity
            else "semantic_alignment_incomplete"
        ),
    }


def _next_action(
    *,
    candidate: Mapping[str, Any] | None,
    blockers: list[str],
    alignment: Mapping[str, Any],
    missing_design: list[str],
    missing_visual: list[str],
) -> str:
    if candidate is None:
        return "SOURCE_REPAIR_REQUIRED"
    if not blockers:
        return "QUALITY_EVIDENCE_COMPLETE"
    if not _text(candidate.get("public_post_text")):
        return "CAPTION_AND_FULL_QUALITY_GENERATION_REQUIRED"
    if alignment.get("joinable") and (missing_design or missing_visual):
        return "JOIN_ALIGNMENT_THEN_GENERATE_DESIGN_EVIDENCE"
    if missing_design or missing_visual:
        return "ALIGNMENT_AND_DESIGN_EVIDENCE_GENERATION_REQUIRED"
    return "QUALITY_EVIDENCE_REGENERATION_REQUIRED"


def build_quality_evidence_audit(
    plan: Mapping[str, Any],
    *,
    semantic_alignment_runs: list[dict[str, Any]],
    content_understanding_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates = _candidate_map(plan)
    diagnostics = _diagnostic_map(plan)
    slots: list[dict[str, Any]] = []

    for account_id in ACCOUNTS:
        for route in ROUTES:
            key = (account_id, route)
            candidate = candidates.get(key)
            if candidate is None:
                slots.append(
                    {
                        "account_id": account_id,
                        "content_route": route,
                        "status": "SOURCE_MISSING",
                        "candidate_blockers": [],
                        "selection_blocked_reasons": _selection_reasons(
                            plan,
                            account_id=account_id,
                            route=route,
                        )[:30],
                        "semantic_evidence": {
                            "match_type": "NONE",
                            "joinable": False,
                        },
                        "understanding_evidence": {
                            "match_type": "NONE",
                            "status": "MISSING",
                        },
                        "missing_public_validation_fields": list(PUBLIC_VALIDATION_FIELDS),
                        "missing_alignment_fields": list(ALIGNMENT_FIELDS),
                        "missing_design_fields": list(DESIGN_FIELDS),
                        "missing_visual_fields": list(VISUAL_FIELDS),
                        "next_action": "SOURCE_REPAIR_REQUIRED",
                    }
                )
                continue

            blockers = [
                str(value)
                for value in diagnostics.get(key, {}).get("blockers", [])
            ]
            semantic, semantic_match_type = _semantic_matches(
                semantic_alignment_runs,
                candidate=candidate,
            )
            understanding, understanding_match_type = _understanding_match(
                content_understanding_runs,
                candidate=candidate,
            )
            alignment = _alignment_recovery(
                candidate,
                semantic,
                semantic_match_type,
            )
            missing_public_validation = _missing_fields(
                candidate,
                PUBLIC_VALIDATION_FIELDS,
            )
            missing_alignment = _missing_fields(candidate, ALIGNMENT_FIELDS)
            missing_design = _missing_fields(candidate, DESIGN_FIELDS)
            missing_visual = _missing_fields(candidate, VISUAL_FIELDS)
            status = (
                "QUALITY_COMPLETE"
                if not blockers
                else "EXISTING_ALIGNMENT_JOINABLE"
                if alignment["joinable"]
                else "QUALITY_EVIDENCE_INCOMPLETE"
            )
            slots.append(
                {
                    "account_id": account_id,
                    "content_route": route,
                    "status": status,
                    "source_post_id": _text(candidate.get("source_post_id")),
                    "source_video_id": _text(candidate.get("source_video_id")),
                    "clip_candidate_id": _text(candidate.get("clip_candidate_id")),
                    "media_asset_id": _text(candidate.get("media_asset_id")),
                    "public_post_text_present": bool(_text(candidate.get("public_post_text"))),
                    "candidate_blockers": blockers,
                    "selection_blocked_reasons": [],
                    "semantic_evidence": alignment,
                    "understanding_evidence": {
                        "match_type": understanding_match_type,
                        "understanding_id": _text(understanding.get("understanding_id")),
                        "status": _text(understanding.get("status")) or "MISSING",
                        "provider_name": _text(understanding.get("provider_name")),
                        "provider_version": _text(understanding.get("provider_version")),
                        "content_hash": _text(understanding.get("content_hash")),
                    },
                    "missing_public_validation_fields": missing_public_validation,
                    "missing_alignment_fields": missing_alignment,
                    "missing_design_fields": missing_design,
                    "missing_visual_fields": missing_visual,
                    "next_action": _next_action(
                        candidate=candidate,
                        blockers=blockers,
                        alignment=alignment,
                        missing_design=missing_design,
                        missing_visual=missing_visual,
                    ),
                }
            )

    complete = sum(1 for slot in slots if slot["status"] == "QUALITY_COMPLETE")
    joinable = sum(1 for slot in slots if slot["status"] == "EXISTING_ALIGNMENT_JOINABLE")
    source_missing = sum(1 for slot in slots if slot["status"] == "SOURCE_MISSING")
    return {
        "status": "READ_ONLY_COMPLETE",
        "audit_status": "PASS" if complete == len(slots) else "BLOCKED",
        "slot_count": len(slots),
        "quality_complete_count": complete,
        "joinable_alignment_count": joinable,
        "source_missing_count": source_missing,
        "slots": slots,
        "safety": {
            "production_write": False,
            "caption_generation": False,
            "evidence_write": False,
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


def load_production_audit() -> dict[str, Any]:
    from config_loader import get_config
    from plan_media_activation_from_production import load_production_plan
    from sheets_client import SheetsClient

    plan = load_production_plan()
    config = get_config()
    client = SheetsClient(config["sheet_id"], config["sa_dict"], dry_run=True)
    return build_quality_evidence_audit(
        plan,
        semantic_alignment_runs=_read_records(client, "semantic_alignment_runs"),
        content_understanding_runs=_read_records(client, "content_understanding_runs"),
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

    report = load_production_audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=== MEDIA ACTIVATION QUALITY EVIDENCE AUDIT ===")
    print(f"READ_STATUS={report['status']}")
    print(f"AUDIT_STATUS={report['audit_status']}")
    print(f"QUALITY_COMPLETE_COUNT={report['quality_complete_count']}")
    print(f"JOINABLE_ALIGNMENT_COUNT={report['joinable_alignment_count']}")
    print(f"SOURCE_MISSING_COUNT={report['source_missing_count']}")
    for slot in report["slots"]:
        identity = (
            slot.get("source_post_id")
            or slot.get("clip_candidate_id")
            or ""
        )
        semantic = slot.get("semantic_evidence", {})
        understanding = slot.get("understanding_evidence", {})
        print(
            "SLOT:"
            f"{slot['account_id']}:"
            f"{slot['content_route']}:"
            f"status={slot['status']}:"
            f"identity={identity}:"
            f"semantic_match={semantic.get('match_type', 'NONE')}:"
            f"semantic_status={semantic.get('status', 'MISSING')}:"
            f"public_hash={semantic.get('public_post_hash_status', 'N/A')}:"
            f"joinable={str(bool(semantic.get('joinable'))).lower()}:"
            f"understanding_match={understanding.get('match_type', 'NONE')}:"
            f"understanding_status={understanding.get('status', 'MISSING')}:"
            f"next_action={slot['next_action']}"
        )
        if slot.get("candidate_blockers"):
            print(
                "CANDIDATE_BLOCKERS:"
                f"{slot['account_id']}:"
                f"{slot['content_route']}:"
                + "|".join(slot["candidate_blockers"])
            )
        if slot.get("selection_blocked_reasons"):
            print(
                "SOURCE_BLOCKERS:"
                f"{slot['account_id']}:"
                f"{slot['content_route']}:"
                + "|".join(slot["selection_blocked_reasons"])
            )
        if semantic.get("recoverable_fields"):
            print(
                "JOINABLE_FIELDS:"
                f"{slot['account_id']}:"
                f"{slot['content_route']}:"
                + "|".join(semantic["recoverable_fields"])
            )
    print(f"REPORT={args.output}")
    print("PASS: Production reads only")
    print("PASS: no generation, evidence mutation, media processing, queue write, workflow dispatch or post")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
