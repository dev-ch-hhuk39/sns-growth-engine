#!/usr/bin/env python3
from create_missing_text_canaries import build_rows

result = build_rows([])
assert result["status"] == "PLAN_ONLY", result
assert len(result["rows"]) == 3
assert {row["canary_id"] for row in result["rows"]} == {"canary_night_scout_original_text", "canary_night_scout_reference_text", "canary_liver_manager_reference_text"}
assert all(row["status"] == "WAITING_REVIEW" and row["validator_status"] == "PASS" for row in result["rows"])
print("PASS")
