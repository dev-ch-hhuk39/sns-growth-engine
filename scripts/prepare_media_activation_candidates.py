#!/usr/bin/env python3
"""Build four review-only media activation queue rows without side effects."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ACCOUNTS = ("night_scout", "liver_manager")
ROUTES = ("direct_reference_media", "approved_source_clip")
APPROVED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}

COMMON_REQUIRED = (
    "public_post_text",
    "source_id",
    "permission_evidence",
    "media_asset_id",
    "media_url",
    "publisher_media_type",
    "final_alignment_score",
    "source_copy_similarity",
    "recent_post_similarity",
    "batch_id",
    "primary_topic",
    "structure_variant",
    "media_primary_topic",
    "visual_topic",
    "visual_text_hash",
    "claim_support_json",
)
PASS_FIELDS = (
    "validator_status",
    "internal_leak_status",
    "account_fit_status",
    "alignment_status",
    "batch_diversity_status",
    "topic_coherence_status",
)
TRUE_FIELDS = (
    "hook_topic_match",
    "closing_topic_match",
    "visual_topic_match",
    "visual_cta_match",
)
EXPECTED_VERSIONS = {
    "quality_gate_version": "generation_quality_v3",
    "feature_schema_version": "post_features_v1",
    "visual_plan_version": "visual_plan_v1",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _truthy(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "pass"}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slot(row: dict[str, Any]) -> tuple[str, str]:
    return (
        _text(row.get("account_id")),
        _text(row.get("content_route") or row.get("canary_type")),
    )


def _identity(row: dict[str, Any]) -> str:
    keys = (
        "account_id",
        "content_route",
        "source_post_id",
        "source_video_id",
        "clip_candidate_id",
        "media_asset_id",
        "public_post_text",
    )
    payload = {key: _text(row.get(key)) for key in keys}
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def candidate_blockers(row: dict[str, Any]) -> list[str]:
    account_id, route = _slot(row)
    blockers: list[str] = []

    if account_id not in ACCOUNTS:
        blockers.append("unsupported_account")
    if route not in ROUTES:
        blockers.append("unsupported_route")

    for field in COMMON_REQUIRED:
        if not _text(row.get(field)):
            blockers.append(f"{field}_missing")

    if route == "direct_reference_media":
        if not _text(row.get("source_post_id")):
            blockers.append("source_post_id_missing")
    elif route == "approved_source_clip":
        for field in ("source_video_id", "clip_candidate_id", "start_seconds", "end_seconds"):
            if not _text(row.get(field)):
                blockers.append(f"{field}_missing")

    if _text(row.get("rights_status")).lower() not in APPROVED_RIGHTS:
        blockers.append("rights_status_not_approved")
    if _text(row.get("permission_status")).lower() != "approved":
        blockers.append("permission_status_not_approved")

    for field in PASS_FIELDS:
        if _text(row.get(field)).upper() != "PASS":
            blockers.append(f"{field}_not_pass")
    for field in TRUE_FIELDS:
        if not _truthy(row.get(field)):
            blockers.append(f"{field}_not_true")
    for field, expected in EXPECTED_VERSIONS.items():
        if _text(row.get(field)) != expected:
            blockers.append(f"{field}_invalid")

    if _number(row.get("topic_confidence")) < 0.70:
        blockers.append("topic_confidence_below_threshold")
    if _number(row.get("main_claim_coverage")) < 1.0:
        blockers.append("main_claim_coverage_below_threshold")
    if int(_number(row.get("unsupported_claim_count"), -1)) != 0:
        blockers.append("unsupported_claims_present")

    return sorted(set(blockers))


def build_queue_row(candidate: dict[str, Any]) -> dict[str, Any]:
    blockers = candidate_blockers(candidate)
    if blockers:
        raise ValueError("candidate_blocked:" + ",".join(blockers))

    account_id, route = _slot(candidate)
    batch_id = _text(candidate.get("batch_id"))
    canary_id = _text(candidate.get("canary_id"))
    if not canary_id.startswith("canary_fresh_"):
        canary_id = (
            f"canary_fresh_media_activation_{batch_id}_{account_id}_{route}"
        )

    queue_id = _text(candidate.get("queue_id"))
    if not queue_id:
        queue_id = f"media_activation_{account_id}_{route}_{_identity(candidate)}"

    generation_mode = (
        "saved_direct_reference_media"
        if route == "direct_reference_media"
        else "saved_approved_source_clip"
    )

    row = dict(candidate)
    row.update(
        {
            "queue_id": queue_id,
            "account_id": account_id,
            "target_account_id": account_id,
            "platform": "threads",
            "status": "WAITING_REVIEW",
            "auto_publish": "false",
            "ai_publish_recommendation": "review",
            "content_route": route,
            "content_type": route,
            "generation_mode": generation_mode,
            "media_required": "true",
            "media_status": "ATTACHED",
            "rights_review_required": "false",
            "excluded_from_activation": "false",
            "excluded_from_metrics_baseline": "false",
            "repost_prohibited": "false",
            "canary_id": canary_id,
            "created_at": _text(candidate.get("created_at")) or _now(),
            "updated_at": _now(),
            "processed_at": "",
            "posted_at": "",
            "post_url": "",
            "result_id": "",
            "error": "",
            "blocked_reason": "",
        }
    )
    return row


def build_plan(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    expected = {(account, route) for account in ACCOUNTS for route in ROUTES}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for candidate in candidates:
        grouped.setdefault(_slot(candidate), []).append(dict(candidate))

    missing = sorted(
        f"{account}:{route}"
        for account, route in expected
        if len(grouped.get((account, route), [])) == 0
    )
    duplicates = sorted(
        f"{account}:{route}"
        for account, route in expected
        if len(grouped.get((account, route), [])) > 1
    )

    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if not missing and not duplicates:
        for account, route in sorted(expected):
            candidate = grouped[(account, route)][0]
            blockers = candidate_blockers(candidate)
            if blockers:
                failures.append(
                    {
                        "account_id": account,
                        "content_route": route,
                        "blockers": blockers,
                    }
                )
            else:
                rows.append(build_queue_row(candidate))

    status = (
        "PASS"
        if len(rows) == 4 and not missing and not duplicates and not failures
        else "BLOCKED"
    )
    return {
        "status": status,
        "expected_row_count": 4,
        "row_count": len(rows),
        "missing_slots": missing,
        "duplicate_slots": duplicates,
        "failures": failures,
        "rows": rows,
        "would_write": False,
        "would_ready": False,
        "would_post": False,
        "would_download": False,
        "would_cut": False,
        "would_upload": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit("input JSON must be a list")

    plan = build_plan([dict(item) for item in payload])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": plan["status"],
                "row_count": plan["row_count"],
                "would_write": False,
                "would_post": False,
            },
            ensure_ascii=False,
        )
    )
    return 0 if plan["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
