#!/usr/bin/env python3
from datetime import datetime, timedelta, timezone

from backfill_missed_content_slots import missing_slots
from content_schedule import slots_for_account
from content_slot_runs import build_slot_run


class Worksheet:
    def __init__(self, rows):
        self.rows = rows

    def get_all_records(self):
        return self.rows


class Client:
    dry_run = False

    def __init__(self, rows):
        self.ws = Worksheet(rows)

    def _ensure_tab(self, _name, _headers):
        return self.ws

    def _call_with_rate_limit_retry(self, _label, operation):
        return operation()


jst = timezone(timedelta(hours=9))
now = datetime(2026, 7, 17, 23, 30, tzinfo=jst)
slot = next(item for item in slots_for_account("liver_manager") if item["target_jst"] == "10:00")
claimed = build_slot_run("liver_manager", slot["slot_id"], status="CLAIMED", now=now)
claimed.update({"claim_status": "CLAIMED", "lease_expires_at": (now + timedelta(minutes=20)).isoformat()})
active_ids = {item["slot_id"] for item in missing_slots(Client([claimed]), "liver_manager", now)}
claimed["lease_expires_at"] = (now - timedelta(minutes=1)).isoformat()
expired_ids = {item["slot_id"] for item in missing_slots(Client([claimed]), "liver_manager", now)}
checks = [
    ("active claim skipped", slot["slot_id"] not in active_ids),
    ("expired claim recoverable", slot["slot_id"] in expired_ids),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
