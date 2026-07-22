#!/usr/bin/env python3
from datetime import datetime, timedelta, timezone

from content_schedule import slots_for_account
from content_slot_runs import _slot_run_contract_issues, build_slot_run, business_date, posts_used_in_business_date

jst = timezone(timedelta(hours=9))
at_0100 = datetime(2026, 7, 18, 1, 0, tzinfo=jst)
slot_25 = next(slot for slot in slots_for_account("night_scout") if slot["target_jst"] == "25:00")
row = build_slot_run("night_scout", slot_25["slot_id"], now=at_0100)
contract_row = dict(row)
bad_contract_row = dict(row)
bad_contract_row["schedule_date_jst"] = "2026-07-18"
posted = [{"account_id": "night_scout", "platform": "threads", "status": "POSTED", "posted_at": at_0100.isoformat()}]
checks = [
    ("04:00 boundary uses previous date", business_date(at_0100) == "2026-07-17"),
    ("25:00 target is next calendar day", row["scheduled_target_at"].startswith("2026-07-18T01:00")),
    ("25:00 row belongs to prior business date", row["schedule_date_jst"] == "2026-07-17"),
    ("daily cap count shares business date", posts_used_in_business_date("night_scout", posted, at_0100) == 1),
    ("slot persistence retains business-date contract", not _slot_run_contract_issues(contract_row, row)),
    ("slot persistence rejects wrong business date", _slot_run_contract_issues(bad_contract_row, row) == ["schedule_date_jst"]),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
