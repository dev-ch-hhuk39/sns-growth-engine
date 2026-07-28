#!/usr/bin/env python3
from evaluate_capability_matrix import evaluate

result = evaluate()
assert result["required"] == 22
assert result["code_complete"] == 22
assert result["production_unverified"] == 22
assert result["status"] == "FAIL", "production evidence must remain fail-closed"
print("PASS test_capability_matrix_separates_code_from_production.py")
