#!/usr/bin/env python3
"""Find overdue unfilled slots; optionally fill each once via the safe fallback."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
from config_loader import get_config  # noqa: E402
from content_schedule import load_content_schedule  # noqa: E402
from content_slot_runs import business_date, existing_slot_status  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402

JST = timezone(timedelta(hours=9))
POSTED = {"POSTED_PRIMARY", "POSTED_FALLBACK", "BACKFILLED"}


def missing_slots(client: SheetsClient, account_id: str, now: datetime | None = None) -> list[dict[str, Any]]:
    local = (now or datetime.now(JST)).astimezone(JST)
    operational_day = datetime.fromisoformat(business_date(local)).date()
    result = []
    for slot in load_content_schedule()["accounts"].get(account_id, []):
        configured_hour, minute = map(int, slot["target_jst"].split(":"))
        target_day = operational_day + timedelta(days=1 if configured_hour >= 24 else 0)
        target = datetime(target_day.year, target_day.month, target_day.day, configured_hour % 24, minute, tzinfo=JST)
        if target > local - timedelta(minutes=20):
            continue
        status = existing_slot_status(client, account_id, slot["slot_id"], local)
        if status not in POSTED:
            result.append({"slot_id": slot["slot_id"], "expected_post_type": slot["post_type"], "status": status or "MISSING", "target_jst": target.isoformat()})
    return sorted(result, key=lambda row: row["target_jst"])


def main() -> int:
    parser = argparse.ArgumentParser(description="detect and one-time backfill missed content slots")
    parser.add_argument("--account-id", default="all", choices=["all", "night_scout", "liver_manager"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-backfill", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.confirm_backfill:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-backfill"})); return 1
    cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    accounts = ["night_scout", "liver_manager"] if args.account_id == "all" else [args.account_id]
    plans = {account: missing_slots(client, account) for account in accounts}
    result: dict[str, Any] = {"status": "PLAN_ONLY", "aftercare_threshold_minutes": 20, "missing_slots": plans, "would_post": False, "backfills": []}
    if not args.apply:
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    if str(os.environ.get("PUBLISH_ENABLED", "")).lower() not in {"1", "true", "yes"} or str(os.environ.get("ALLOW_REAL_THREADS_POST", "")).lower() not in {"1", "true", "yes"}:
        print(json.dumps({**result, "status": "BLOCKED", "reason": "Threads publishing gates are required"}, ensure_ascii=False, indent=2)); return 1
    from run_slot_text_fallback import build_plan, execute
    # One late post per account/run; the fallback runner re-checks idempotency.
    for account, slots in plans.items():
        if not slots:
            continue
        slot = slots[0]
        fallback = execute(build_plan(account, slot["slot_id"], "missed_slot_aftercare", apply=True), client)
        result["backfills"].append({"account_id": account, "slot_id": slot["slot_id"], "result": fallback.get("status", "FAILED")})
    result["status"] = "BACKFILLED" if any(row["result"] == "POSTED" for row in result["backfills"]) else "NO_POST"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
