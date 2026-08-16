#!/usr/bin/env python3
from verify_reference_first_integration import verify_all

result = verify_all()
assert result["status"] == "PASS", result
assert result["external_calls"] is False
assert result["production_writes"] is False
for account_id in ("night_scout", "liver_manager"):
    row = result["accounts"][account_id]
    assert row["status"] == "PASS", row
    assert all(row["checks"].values()), row
    assert row["queue_status"] == "WAITING_REVIEW"
    assert row["publisher_eligible"] is False
    assert row["aspect_ratio"] == "16:9"
print("PASS test_reference_first_integration_verification.py")
