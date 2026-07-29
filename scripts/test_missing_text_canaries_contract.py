#!/usr/bin/env python3
from create_missing_text_canaries import build_rows

result = build_rows([])
assert result["status"] == "PLAN_ONLY", result
assert len(result["rows"]) == 4
assert {(row["account_id"], row["generation_mode"]) for row in result["rows"]} == {("night_scout", "original_text"), ("night_scout", "reference_text"), ("liver_manager", "original_text"), ("liver_manager", "reference_text")}
assert all(row["canary_id"].startswith("canary_fresh_") for row in result["rows"])
assert all(row["status"] == "WAITING_REVIEW" and row["validator_status"] == "PASS" for row in result["rows"])
print("PASS")
