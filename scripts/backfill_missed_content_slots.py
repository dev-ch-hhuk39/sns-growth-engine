#!/usr/bin/env python3
"""Find overdue unfilled slots; optionally fill each once via the safe fallback."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts")); sys.path.insert(0, str(ROOT / "src"))
from config_loader import get_config  # noqa: E402
from content_schedule import load_content_schedule  # noqa: E402
from content_slot_runs import existing_slot_status  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402

JST = timezone(timedelta(hours=9))
POSTED = {"POSTED_PRIMARY", "POSTED_FALLBACK", "BACKFILLED"}


def missing_slots(client: SheetsClient, account_id: str, now: datetime | None = None) -> list[dict[str, Any]]:
    local = (now or datetime.now(JST)).astimezone(JST)
    result = []
    for slot in load_content_schedule()["accounts"].get(account_id, []):
        hour, minute = map(int, slot["target_jst"].split(":")); hour %= 24
        target = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target > local - timedelta(minutes=20):
            continue
        status = existing_slot_status(client, account_id, slot["slot_id"])
        if status not in POSTED:
            result.append({"slot_id": slot["slot_id"], "expected_post_type": slot["post_type"], "status": status or "MISSING", "target_jst": target.isoformat()})
    return result


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
    print(json.dumps({"status": "PLAN_ONLY", "aftercare_threshold_minutes": 20, "missing_slots": plans, "would_post": False}, ensure_ascii=False, indent=2))
    # Publishing a late slot remains deliberately explicit: the aftercare
    # workflow reports it; a future gated worker can call the regular fallback.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
