#!/usr/bin/env python3
"""Normalize the newest exact-slot media caption before Hybrid review."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from config_loader import get_config  # noqa: E402
from scheduled_caption_policy import normalize_scheduled_caption  # noqa: E402
from scheduled_execution_guard import append_job_summary  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
PROTECTED_QUEUE_IDS = {
    "media_activation_liver_manager_approved_source_clip_c92d646a523bdbb5",
    "media_activation_liver_manager_direct_reference_media_177110184f553b45",
    "media_activation_night_scout_approved_source_clip_5698ff0b9340c2e7",
    "media_activation_night_scout_direct_reference_media_3921883bd6b80076",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"])
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if not args.use_sheets:
        raise RuntimeError("--use-sheets is required")

    cfg = get_config()
    client = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=False)
    rows = [
        dict(row)
        for row in client.get_queue_items(
            account_id=args.account_id,
            platform="threads",
            status="WAITING_REVIEW",
        )
        if str(row.get("slot_id", "")) == args.slot_id
        and str(row.get("queue_id", "")) not in PROTECTED_QUEUE_IDS
        and str(row.get("excluded_from_activation", "")).lower() not in {"true", "1", "yes"}
        and str(row.get("repost_prohibited", "")).lower() not in {"true", "1", "yes"}
    ]
    rows.sort(key=lambda row: (str(row.get("created_at", "")), str(row.get("queue_id", ""))), reverse=True)
    if not rows:
        payload = {
            "status": "NO_POST",
            "reason": "no_waiting_review_candidate_for_exact_slot",
            "account_id": args.account_id,
            "slot_id": args.slot_id,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        append_job_summary("Scheduled caption normalization", payload)
        return 2

    row = rows[0]
    queue_id = str(row.get("queue_id", ""))
    media_origin = str(row.get("media_origin", ""))
    result = normalize_scheduled_caption(
        args.account_id,
        row.get("public_post_text", ""),
        media_origin=media_origin,
    )
    payload = {
        **result,
        "account_id": args.account_id,
        "slot_id": args.slot_id,
        "queue_id": queue_id,
        "media_origin": media_origin,
        "apply": args.apply,
    }
    if result["status"] != "PASS":
        if args.apply:
            client.update_queue_item(
                queue_id,
                validator_status="BLOCKED",
                text_policy_status="BLOCKED",
                account_fit_status="BLOCKED",
                blocked_reason=",".join(result["blocked_reasons"]),
                error=",".join(result["blocked_reasons"]),
                updated_at=datetime.now(JST).isoformat(),
            )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        append_job_summary("Scheduled caption normalization: BLOCKED", payload)
        return 2

    if args.apply:
        client.update_queue_item(
            queue_id,
            public_post_text=result["public_post_text"],
            caption_provider="scheduled_caption_policy",
            caption_provider_version=result["policy_version"],
            validator_status="PASS",
            text_policy_status="PASS",
            account_fit_status="PASS",
            blocked_reason="",
            error="",
            updated_at=datetime.now(JST).isoformat(),
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    append_job_summary("Scheduled caption normalization: PASS", payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
