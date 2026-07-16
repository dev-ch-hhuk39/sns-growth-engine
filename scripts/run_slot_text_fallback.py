#!/usr/bin/env python3
"""Post one validator-safe text fallback when a scheduled media slot has no asset.

This runner is deliberately narrow: it is called only by a named slot and uses
the normal Threads queue worker, so every regular posting, duplicate, and
public-text safety check remains in force.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_config  # noqa: E402
from content_schedule import slot_by_id  # noqa: E402
from content_slot_runs import business_date, build_slot_run, claim_slot_run, existing_slot_status, posts_used_in_business_date, upsert_slot_run  # noqa: E402
from process_threads_queue import append_row, process_one  # noqa: E402
from public_post_quality import final_public_post_validator, generate_reader_facing_post, public_preview  # noqa: E402
from sheets_client import TAB_DEFINITIONS, SheetsClient  # noqa: E402

POSTED_SLOT_STATUSES = {"POSTED_PRIMARY", "POSTED_FALLBACK", "BACKFILLED"}


def _true(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def build_plan(account_id: str, slot_id: str, reason: str, *, apply: bool, attempt: int = 1) -> dict[str, Any]:
    slot = slot_by_id(account_id, slot_id)
    if not slot:
        return {"status": "BLOCKED", "blocked_reasons": ["unknown_content_slot"]}
    jst = timezone(timedelta(hours=9))
    schedule_date = business_date(datetime.now(jst))
    index = ((sum(ord(char) for char in f"{account_id}|{slot_id}|{schedule_date}|{reason}") + attempt * 7) % 20) + 1
    text = generate_reader_facing_post(account_id, index=index)
    validation = final_public_post_validator(text, account_id)
    return {
        "status": "WILL_APPLY" if apply and validation["status"] == "PASS" else "PLAN_ONLY" if validation["status"] == "PASS" else "BLOCKED",
        "account_id": account_id,
        "slot_id": slot_id,
        "expected_post_type": slot["post_type"],
        "actual_post_type": "reference_text" if slot["post_type"] in {"direct_reference_media", "generated_clip_media"} else "original_text",
        "fallback_level": 3 if slot["post_type"] in {"direct_reference_media", "generated_clip_media"} else 1,
        "fallback_reason": reason,
        "schedule_date_jst": schedule_date,
        "variant_attempt": attempt,
        "public_post_text": text,
        "public_post_preview": public_preview(text),
        "final_public_post_validator": validation["status"],
        "would_post": bool(apply and validation["status"] == "PASS"),
        "blocked_reasons": validation.get("blocked_reasons", []),
    }


def execute(plan: dict[str, Any], client: SheetsClient) -> dict[str, Any]:
    account_id = str(plan["account_id"])
    slot_id = str(plan["slot_id"])
    client._ensure_tab("posted_results", TAB_DEFINITIONS["posted_results"])
    posted_rows = client._call_with_rate_limit_retry(
        "get_all_records:posted_results:slot_fallback",
        lambda: client._ws("posted_results").get_all_records(),
    )
    autonomous = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
    daily_cap = int(autonomous.get("daily_post_cap_per_account", 5))
    if posts_used_in_business_date(account_id, [dict(row) for row in posted_rows]) >= daily_cap:
        return {**plan, "status": "SKIPPED", "reason": "daily_post_cap_reached", "would_post": False}
    claim = claim_slot_run(client, account_id, slot_id)
    if claim.get("status") != "CLAIMED":
        return {**plan, "status": "SKIPPED", "reason": claim.get("reason", "slot_not_claimed"), "would_post": False}
    started = build_slot_run(account_id, slot_id, status="RUNNING", actual_post_type=plan["actual_post_type"], fallback_level=int(plan["fallback_level"]), no_post_reason=plan["fallback_reason"], claim_status="CLAIMED", publish_attempt_id=claim.get("slot_run_id", ""))
    upsert_slot_run(client, started)
    queue_id = f"slot_fallback_{started['schedule_date_jst'].replace('-', '')}_{account_id}_{slot_id}_{plan['variant_attempt']}"
    queue = {
        "queue_id": queue_id,
        "account_id": account_id,
        "target_account_id": account_id,
        "platform": "threads",
        "priority": "1",
        "status": "READY",
        "auto_publish": "true",
        "generation_mode": f"slot_fallback_{plan['expected_post_type']}",
        "public_post_text": plan["public_post_text"],
        "validator_status": "PASS",
        "internal_leak_status": "PASS",
        "account_fit_status": "PASS",
        "media_required": "false",
        "media_reuse_risk": "not_applicable",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    append_row(client, "queue", queue)
    result = process_one(client, queue, dry_run=False, confirm_real_post=True)
    # A duplicate is recoverable: produce up to three daily/history-varying
    # variants instead of leaving a scheduled slot empty.
    if str(result.get("status", "")) == "DUPLICATE_BLOCKED" and int(plan["variant_attempt"]) < 3:
        return execute(build_plan(account_id, slot_id, plan["fallback_reason"], apply=True, attempt=int(plan["variant_attempt"]) + 1), client)
    posted = str(result.get("status", "")) == "POSTED"
    completed = build_slot_run(
        account_id,
        slot_id,
        status="POSTED_FALLBACK" if posted else "FAILED",
        actual_post_type=plan["actual_post_type"],
        fallback_level=int(plan["fallback_level"]),
        no_post_reason="" if posted else str(result.get("reason", result.get("status", "fallback_failed"))),
        queue_id=queue_id,
        result_id=result.get("result_id", ""),
        post_url=result.get("post_url", ""),
        actual_posted_at=datetime.now(timezone.utc).isoformat() if posted else "",
    )
    upsert_slot_run(client, completed)
    return {**plan, "status": result.get("status", "FAILED"), "queue_id": queue_id, "post_result": result, "would_post": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="post a named slot's safe text fallback")
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"])
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--reason", default="media_asset_unavailable")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-slot-fallback", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.confirm_slot_fallback:
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["--apply requires --confirm-slot-fallback"]}, ensure_ascii=False))
        return 1
    plan = build_plan(args.account_id, args.slot_id, args.reason, apply=args.apply)
    if args.apply:
        if not args.use_sheets:
            plan = {**plan, "status": "BLOCKED", "blocked_reasons": ["--use-sheets required"]}
        elif not (_true(os.environ.get("PUBLISH_ENABLED")) and _true(os.environ.get("ALLOW_REAL_THREADS_POST"))):
            plan = {**plan, "status": "BLOCKED", "blocked_reasons": ["Threads publishing env gates are required"]}
        elif plan["status"] != "BLOCKED":
            cfg = get_config()
            plan = execute(plan, SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False))
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 1 if plan.get("status") in {"BLOCKED", "FAILED"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
