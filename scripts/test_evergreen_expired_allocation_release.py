#!/usr/bin/env python3
"""Contracts for reclaiming only safe, expired evergreen allocations."""
from datetime import datetime
from types import SimpleNamespace

from evergreen_inventory import (
    expired_unpublished_bank_allocations,
    release_expired_unpublished_bank_allocations,
)


def queue(**overrides):
    row = {
        "queue_id": "q1", "account_id": "night_scout", "target_account_id": "night_scout",
        "platform": "threads", "status": "READY", "validator_status": "PASS",
        "internal_leak_status": "PASS", "account_fit_status": "PASS",
        "public_post_text": "安全な予備本文です。", "slot_id": "ns_1600_original",
        "business_date_jst": "2026-09-10", "schedule_date_jst": "2026-09-10",
    }
    row.update(overrides)
    return row


bank = [{"queue_id": "q1", "account_id": "night_scout", "status": "VALIDATED"}]
safe = expired_unpublished_bank_allocations(bank, [queue()], [], [], current_business_date="2026-09-15")
assert len(safe) == 1 and safe[0]["fields"] == {"slot_id": "", "business_date_jst": "", "schedule_date_jst": ""}

assert not expired_unpublished_bank_allocations(bank, [queue()], [{"queue_id": "q1"}], [], current_business_date="2026-09-15")
assert not expired_unpublished_bank_allocations(bank, [queue()], [], [{
    "account_id": "night_scout", "slot_id": "ns_1600_original", "schedule_date_jst": "2026-09-10",
    "status": "RECOVERY_REQUIRED",
}], current_business_date="2026-09-15")
assert not expired_unpublished_bank_allocations(bank, [queue(business_date_jst="2026-09-15", schedule_date_jst="2026-09-15")], [], [], current_business_date="2026-09-15")
assert not expired_unpublished_bank_allocations(bank, [queue(business_date_jst="2026-09-16", schedule_date_jst="2026-09-16")], [], [], current_business_date="2026-09-15")


class Worksheet:
    def __init__(self):
        self.values = [["queue_id", "slot_id", "business_date_jst", "schedule_date_jst"],
                       ["q1", "ns_1600_original", "2026-09-10", "2026-09-10"]]

    def get_all_values(self):
        return self.values

    def batch_update(self, updates, *, value_input_option):
        assert value_input_option == "RAW"
        for update in updates:
            column = ord(update["range"][0]) - ord("A")
            self.values[1][column] = update["values"][0][0]


ws = Worksheet()
client = SimpleNamespace(_ws=lambda logical: ws)
result = release_expired_unpublished_bank_allocations(client, safe, apply=True)
assert result == {"status": "RELEASED", "released": 1, "read_after_write": "PASS", "would_post": False}
assert ws.values[1] == ["q1", "", "", ""]
print("PASS test_evergreen_expired_allocation_release.py")
