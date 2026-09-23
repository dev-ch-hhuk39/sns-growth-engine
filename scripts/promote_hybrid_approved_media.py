#!/usr/bin/env python3
"""Promote only explicitly selected Hybrid-approved media queue rows."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from config_loader import get_config  # noqa: E402
from accounts.managed_accounts import (  # noqa: E402
    account_allows_autonomous_ready,
    account_choices,
    managed_account,
)
from hybrid_ai_gate import hybrid_ai_gate_passed  # noqa: E402
from hybrid_ai_policy import requires_hybrid_ai_gate  # noqa: E402
from hybrid_ai_source_context import build_source_context  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from sheets_record_reader import read_records_safely  # noqa: E402
from media_post_validator import validate_media_post  # noqa: E402
from media_v1_policy import hard_gate_fields, warning_fields  # noqa: E402

MEDIA_MODES = {
    "direct_reference_media",
    "saved_direct_reference_media",
    "approved_source_clip",
    "saved_approved_source_clip",
    "system_owned_media",
}
ALLOWED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def is_media(row: dict[str, Any]) -> bool:
    mode = str(row.get("generation_mode") or row.get("content_type") or "").lower()
    return mode in MEDIA_MODES or truthy(row.get("media_required"))


def media_validation_plan(row: dict[str, Any]) -> dict[str, Any]:
    media_url = str(row.get("media_url") or row.get("storage_url") or "").strip()
    return {
        "rights_status": row.get("rights_status", ""),
        "permission_status": row.get("permission_status", ""),
        "media_url": media_url,
        "media_asset_id": row.get("media_asset_id", ""),
        "platform": row.get("platform", "threads"),
        "account_id": row.get("account_id", ""),
        "target_account_id": row.get("target_account_id") or row.get("account_id", ""),
        "media_type": row.get("media_type", "video"),
        "content_type": row.get("content_type") or row.get("content_route", ""),
        "publisher_media_type": row.get("publisher_media_type", ""),
        "media_urls": [media_url] if media_url else [],
        "duration_seconds": row.get("duration_seconds", 0),
        "aspect_ratio": row.get("aspect_ratio", ""),
        "aspect_ratio_policy": row.get("aspect_ratio_policy", "preserve_source"),
        "source_aspect_ratio": row.get("source_aspect_ratio", ""),
        "width": row.get("width", ""),
        "height": row.get("height", ""),
        "video_stream_count": row.get("video_stream_count", 0),
        "audio_stream_count": row.get("audio_stream_count", 0),
        "media_probe_status": row.get("media_probe_status", ""),
        "enforce_video_stream_evidence": row.get("enforce_video_stream_evidence", "false"),
        "public_post_text": row.get("public_post_text", ""),
        "media_origin": row.get("media_origin", "approved_source_clip"),
        "caption_mode": row.get("caption_mode", "transform"),
        "alignment_status": row.get("alignment_status", ""),
        "final_alignment_score": row.get("final_alignment_score", ""),
        "main_claim_coverage": row.get("main_claim_coverage", ""),
        "unsupported_claim_count": row.get("unsupported_claim_count", ""),
        "source_copy_similarity": row.get("source_copy_similarity", ""),
        "recent_post_similarity": row.get("recent_post_similarity", ""),
    }


def build_plan(
    client: SheetsClient,
    account_id: str,
    slot_id: str,
    queue_ids: set[str] | None = None,
    *,
    autonomous_low_risk: bool = False,
) -> dict[str, Any]:
    requested = set(queue_ids or set())
    rows = [dict(row) for row in read_records_safely(client, "queue")]
    posted = [dict(row) for row in read_records_safely(client, "posted_results")]
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for row in rows:
        queue_id = str(row.get("queue_id", ""))
        if requested and queue_id not in requested:
            continue
        if str(row.get("account_id") or row.get("target_account_id") or "") != account_id:
            continue
        if str(row.get("target_account_id") or account_id) != account_id:
            rejected.append({"queue_id": queue_id, "reasons": "account_namespace_mismatch"})
            continue
        if str(row.get("slot_id", "")) != slot_id:
            continue
        expected_status = "WAITING_REVIEW" if autonomous_low_risk else "READY"
        if str(row.get("status", "")).upper() != expected_status:
            continue
        if autonomous_low_risk:
            if not account_allows_autonomous_ready(account_id):
                rejected.append({"queue_id": queue_id, "reasons": "account_requires_human_review"})
                continue
        elif str(row.get("human_review_decision", "")).upper() != "OK":
            rejected.append({"queue_id": queue_id, "reasons": "human_review_not_approved"})
            continue
        if truthy(row.get("excluded_from_activation")) or truthy(row.get("repost_prohibited")):
            continue
        reasons: list[str] = []
        if not is_media(row):
            reasons.append("not_media")
        hybrid_required = requires_hybrid_ai_gate(row)
        gate_ok, gate_reason = hybrid_ai_gate_passed(row, build_source_context(client, row))
        if str(row.get("rights_status", "")).lower() not in ALLOWED_RIGHTS:
            reasons.append("rights_not_allowed")
        if str(row.get("permission_status", "")).lower() not in {"approved", "not_required"}:
            reasons.append("permission_not_approved")
        media_url = str(
            row.get("media_url")
            or row.get("storage_url")
            or row.get("media_urls_json")
            or ""
        ).strip()
        if not media_url:
            reasons.append("media_url_missing")
        identities = {
            "media_asset_id": str(row.get("media_asset_id", "")),
            "source_post_id": str(row.get("source_post_id", "")),
            "source_video_id": str(row.get("source_video_id", "")),
            "clip_candidate_id": str(row.get("clip_candidate_id") or row.get("video_clip_id") or ""),
        }
        for posted_row in posted:
            if str(posted_row.get("account_id", "")) != account_id:
                continue
            if any(value and str(posted_row.get(field, "")) == value for field, value in identities.items()):
                reasons.append("media_identity_already_posted")
                break
        validation = validate_media_post(media_validation_plan(row))
        reasons.extend(validation.get("blocked_reasons", []))
        if reasons:
            rejected.append({"queue_id": queue_id, "reasons": ",".join(reasons)})
            continue
        soft = list(validation.get("soft_warning_codes", []))
        if not hybrid_required:
            soft.append("HYBRID_AI_NOT_REQUIRED_FOR_ROUTE")
        if not gate_ok:
            soft.append(f"HYBRID_AI_{gate_reason.upper()}")
        selected.append({
            **row,
            **hard_gate_fields([]),
            **warning_fields(soft),
            "human_review_status": str(row.get("human_review_status") or "UNREVIEWED"),
        })
    selected.sort(
        key=lambda row: (
            int(str(row.get("priority", "999") or "999")),
            str(row.get("created_at", "")),
            str(row.get("queue_id", "")),
        )
    )
    chosen = selected[:1]
    return {
        "status": "PLAN_READY",
        "account_id": account_id,
        "slot_id": slot_id,
        "requested_queue_ids": sorted(requested),
        "selected_queue_ids": [str(row.get("queue_id", "")) for row in chosen],
        "updated_queue_ids": [],
        "rejected": rejected[:20],
        "promotion_fields": {
            str(row.get("queue_id", "")): {
                **hard_gate_fields([]),
                **warning_fields(json.loads(str(row.get("soft_warning_codes") or "[]"))),
                "human_review_status": str(row.get("human_review_status") or "UNREVIEWED"),
            }
            for row in chosen
        },
        "would_post": False,
    }


def apply(client: SheetsClient, result: dict[str, Any], *, autonomous_low_risk: bool = False) -> dict[str, Any]:
    updated: list[str] = []
    policy = str(managed_account(result["account_id"]).get("review_policy", ""))
    approval_source = policy if autonomous_low_risk else "human_review"
    for queue_id in result["selected_queue_ids"]:
        media_fields = dict(result.get("promotion_fields", {}).get(queue_id, {}))
        client.update_queue_item(
            queue_id,
            status="READY",
            auto_publish="true" if autonomous_low_risk else "false",
            approval_source=approval_source,
            approval_policy=policy,
            blocked_reason="",
            error="",
            auto_ready_by="promote_hybrid_approved_media.py",
            auto_ready_reason=(
                f"{policy}_hybrid_ai_and_persisted_media_validators_passed"
                if autonomous_low_risk
                else "human_review_hybrid_ai_and_persisted_media_validators_passed"
            ),
            **media_fields,
        )
        updated.append(queue_id)
    rows_after = {
        str(row.get("queue_id", "")): dict(row)
        for row in read_records_safely(client, "queue")
    }
    read_after_write = all(
        str(rows_after.get(queue_id, {}).get("status", "")).upper() == "READY"
        and str(rows_after.get(queue_id, {}).get("auto_ready_by", ""))
        == "promote_hybrid_approved_media.py"
        for queue_id in updated
    )
    if updated and not read_after_write:
        raise RuntimeError("media_ready_read_after_write_failed")
    return {
        **result,
        "status": "APPLIED",
        "updated_queue_ids": updated,
        "updated_count": len(updated),
        "read_after_write": read_after_write,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True, choices=account_choices())
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--queue-id", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-promote", action="store_true")
    parser.add_argument("--autonomous-low-risk", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if args.apply == args.dry_run:
        raise RuntimeError("specify exactly one of --apply or --dry-run")
    if args.apply and not args.confirm_promote:
        raise RuntimeError("--apply requires --confirm-promote")
    if args.autonomous_low_risk and not account_allows_autonomous_ready(args.account_id):
        raise RuntimeError("autonomous_low_risk_not_allowed_for_account")
    if not args.use_sheets:
        raise RuntimeError("--use-sheets is required")
    if not args.queue_id:
        raise RuntimeError("at least one --queue-id is required")
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    result = build_plan(
        client,
        args.account_id,
        args.slot_id,
        set(args.queue_id),
        autonomous_low_risk=args.autonomous_low_risk,
    )
    if args.apply:
        result = apply(client, result, autonomous_low_risk=args.autonomous_low_risk)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
