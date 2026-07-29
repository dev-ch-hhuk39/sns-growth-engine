#!/usr/bin/env python3
"""Build the final human-reviewed twelve-item production canary plan.

This command never reads credentials, mutates Sheets, fetches media, or posts.
It describes the exact evidence each approved candidate must have before a
single-item manual canary can be dispatched.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANARY_TYPES = ("original_text", "reference_text", "direct_image", "direct_video", "direct_carousel", "generated_clip")
ACCOUNTS = ("night_scout", "liver_manager")


def required_fields(canary_type: str) -> tuple[str, ...]:
    common = ("account_id", "source_id", "rights_status", "permission_status", "permission_evidence", "public_post_text")
    if canary_type in {"original_text", "reference_text"}:
        return ("account_id", "public_post_text", "queue_id", "persona_validator_status", "final_public_post_validator_status", "internal_leak_status")
    validated_media = ("queue_id", "persona_validator_status", "final_public_post_validator_status", "internal_leak_status", "publisher_media_type")
    if canary_type == "generated_clip":
        return common + validated_media + ("source_video_id", "clip_candidate_id", "local_path", "start_seconds", "end_seconds")
    if canary_type == "direct_carousel":
        return common + validated_media + ("source_post_id", "media_asset_ids", "media_order")
    return common + validated_media + ("source_post_id", "media_asset_id", "media_url")


def build_plan(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    by_key = {(str(row.get("account_id", "")), str(row.get("canary_type", ""))): row for row in candidates}
    for account_id in ACCOUNTS:
        for canary_type in CANARY_TYPES:
            candidate = dict(by_key.get((account_id, canary_type), {}))
            required = required_fields(canary_type)
            missing = [
                field for field in required
                if candidate.get(field) is None
                or (isinstance(candidate.get(field), str) and not candidate.get(field).strip())
                or candidate.get(field) == []
            ]
            is_text = canary_type in {"original_text", "reference_text"}
            rights_ok = is_text or str(candidate.get("rights_status", "")) in {"owned", "licensed", "approved_creator_clip"}
            permission_ok = is_text or str(candidate.get("permission_status", "")) == "approved"
            validator_fields = ("persona_validator_status", "final_public_post_validator_status", "internal_leak_status")
            validators_ok = all(str(candidate.get(field, "")).upper() == "PASS" for field in validator_fields)
            status = "READY_FOR_HUMAN_CANARY" if candidate and not missing and rights_ok and permission_ok and validators_ok else "PENDING_EVIDENCE"
            rows.append({
                "canary_id": str(candidate.get("canary_id") or f"canary_{account_id}_{canary_type}"),
                "account_id": account_id,
                "canary_type": canary_type,
                "status": status,
                "missing_evidence": missing + ([] if rights_ok else ["approved_rights_status"]) + ([] if permission_ok else ["permission_status=approved"]) + ([] if validators_ok else ["media_validators=PASS"]),
                "publish_limit": 1,
                "required_read_after_write": ["Threads post URL", "posted_results result_id", "media asset provenance", "metrics 24h/72h/7d jobs"],
                "rollback": "set kill_switch=true; preserve posted result; do not retry the same idempotency key",
            })
    return {"status": "PLAN_ONLY", "total_canaries": len(rows), "accounts": list(ACCOUNTS), "canaries": rows, "would_fetch": False, "would_write": False, "would_upload": False, "would_post": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", default="", help="optional candidate fixture; never a live Sheets read")
    args = parser.parse_args()
    candidates: list[dict[str, Any]] = []
    if args.input_json:
        candidates = list(json.loads(Path(args.input_json).read_text(encoding="utf-8")).get("candidates", []))
    print(json.dumps(build_plan(candidates), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
