#!/usr/bin/env python3
"""Turn an existing read-only media audit into a fail-closed human review plan.

Offline transformation only: no Sheets, media API, READY updates or publishing.
The output intentionally excludes caption text, source URLs, transcript and secrets.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

MEDIA_SLOTS = {
    ("night_scout", "ns_1800_direct_media"): "direct_reference_media",
    ("night_scout", "ns_2100_clip_media"): "approved_source_clip",
    ("liver_manager", "lm_1600_direct_media"): "direct_reference_media",
    ("liver_manager", "lm_1800_clip_media"): "approved_source_clip",
}

RIGHTS_OK = {"APPROVED", "AUTHORIZED", "GRANTED", "PASS", "ALLOWED"}
SAFE_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")


def _id(value: Any) -> str:
    candidate = str(value or "").strip()
    return candidate if SAFE_ID.fullmatch(candidate) else ""


def _approved(value: Any) -> bool:
    return str(value or "").strip().upper() in RIGHTS_OK


def _passed(value: Any) -> bool:
    return str(value or "").strip().upper() == "PASS"


def _review_candidate(
    row: dict[str, Any], account_id: str, slot_id: str, post_type: str,
) -> dict[str, Any]:
    blockers: set[str] = set()
    queue_id = _id(row.get("queue_id"))
    if not queue_id:
        blockers.add("queue_identifier_unverifiable")
    if str(row.get("status") or "").strip().upper() != "READY":
        blockers.add("candidate_not_ready")
    if not _approved(row.get("rights_status")):
        blockers.add("rights_human_verification_required")
    if not _approved(row.get("permission_status")):
        blockers.add("permission_human_verification_required")
    for field, reason in (
        ("validator_status", "technical_validator_not_passed"),
        ("internal_leak_status", "internal_leak_review_not_passed"),
        ("account_fit_status", "account_fit_review_not_passed"),
        ("alignment_status", "source_alignment_review_not_passed"),
        ("hybrid_ai_status", "hybrid_ai_review_not_passed"),
    ):
        if not _passed(row.get(field)):
            blockers.add(reason)
    quality = row.get("quality_review")
    if not isinstance(quality, dict) or quality.get("pass") is not True:
        blockers.add("caption_quality_review_required")
    if not (row.get("media_asset_id") or row.get("media_url")):
        blockers.add("prepared_media_missing")
    if post_type == "approved_source_clip":
        clip = row.get("clip_contract")
        clip = clip if isinstance(clip, dict) else {}
        for field, reason in (
            ("clip_candidate_present", "clip_candidate_evidence_missing"),
            ("source_video_present", "source_video_evidence_missing"),
            ("duration_in_review_range_8_to_45_seconds", "clip_duration_unverified"),
            ("evidence_present", "clip_evidence_map_missing"),
        ):
            if clip.get(field) is not True:
                blockers.add(reason)
    else:
        direct = row.get("direct_reuse_contract")
        direct = direct if isinstance(direct, dict) else {}
        if direct.get("source_identity_present") is not True:
            blockers.add("original_source_identity_missing")
        if direct.get("source_text_available_for_reuse_check") is not True:
            blockers.add("source_text_comparison_unavailable")

    urgent = {"rights_human_verification_required", "permission_human_verification_required",
              "queue_identifier_unverifiable"}
    return {
        "account_id": account_id,
        "slot_id": slot_id,
        "post_type": post_type,
        "queue_id": queue_id,
        "review_state": "ACTION_REQUIRED" if blockers else "FINAL_HUMAN_REVIEW_REQUIRED",
        "priority": "P1" if blockers & urgent else ("P2" if blockers else "P3"),
        "blockers": sorted(blockers),
        "human_approval_required": True,
        "publish_authorized": False,
    }


def build_plan(audit: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(audit, dict):
        raise ValueError("audit_report_invalid")
    if (
        audit.get("status") != "AUDIT_COMPLETE"
        or audit.get("would_post") is not False
        or audit.get("writes_performed") is not False
        or audit.get("protected_rows_unchanged_during_audit") is not True
        or audit.get("protected_required_values_all_match") is not True
    ):
        raise ValueError("audit_safety_invariants_not_verified")
    slots = audit.get("media_slots")
    if not isinstance(slots, list) or len(slots) != len(MEDIA_SLOTS):
        raise ValueError("media_slot_set_incomplete")

    findings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("media_slot_invalid")
        account = str(slot.get("account_id") or "")
        slot_id = str(slot.get("slot_id") or "")
        post_type = str(slot.get("post_type") or "")
        key = (account, slot_id)
        if key in seen or MEDIA_SLOTS.get(key) != post_type:
            raise ValueError("media_slot_identity_invalid")
        seen.add(key)
        queue = slot.get("queue")
        if not isinstance(queue, dict):
            raise ValueError("media_slot_queue_missing")
        candidates = queue.get("exact_candidates")
        if not isinstance(candidates, list):
            raise ValueError("media_exact_candidates_invalid")
        if not candidates:
            fallback = queue.get("recent_account_media_when_exact_missing")
            findings.append({
                "account_id": account, "slot_id": slot_id, "post_type": post_type,
                "queue_id": "", "review_state": "MISSING_EXACT_CANDIDATE",
                "priority": "P1", "blockers": ["exact_slot_candidate_missing"],
                "other_slot_candidates_not_promoted": len(fallback) if isinstance(fallback, list) else 0,
                "human_approval_required": True, "publish_authorized": False,
            })
            continue
        for candidate in candidates[:5]:
            if not isinstance(candidate, dict):
                raise ValueError("media_candidate_invalid")
            findings.append(_review_candidate(candidate, account, slot_id, post_type))

    if seen != set(MEDIA_SLOTS):
        raise ValueError("media_slot_set_incomplete")
    findings.sort(key=lambda item: (
        {"P1": 0, "P2": 1, "P3": 2}[item["priority"]],
        item["account_id"], item["slot_id"], item["queue_id"],
    ))
    return {
        "schema_version": "sns_media_human_review_plan_v1",
        "status": "HUMAN_REVIEW_REQUIRED",
        "slot_count": len(seen),
        "review_item_count": len(findings),
        "priority_counts": {p: sum(item["priority"] == p for item in findings)
                            for p in ("P1", "P2", "P3")},
        "items": findings,
        "would_post": False,
        "writes_performed": False,
        "ready_transitions_performed": False,
        "publish_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-json", type=Path, required=True,
                        help="Existing run_scheduled_autopost_readonly_audit.py JSON output")
    parser.add_argument("--output-json", type=Path, help="Optional new local report; never overwritten")
    args = parser.parse_args()
    try:
        audit = json.loads(args.audit_json.read_text(encoding="utf-8"))
        plan = build_plan(audit)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        # Fail closed; do not echo sensitive input contents or path.
        print("REVIEW_PLAN_BLOCKED:" + type(exc).__name__)
        return 2
    output = json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output_json:
        try:
            with args.output_json.open("x", encoding="utf-8") as stream:
                stream.write(output)
        except OSError:
            print("REVIEW_PLAN_OUTPUT_BLOCKED")
            return 2
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
