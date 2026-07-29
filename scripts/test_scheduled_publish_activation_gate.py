#!/usr/bin/env python3
from scheduled_publish_activation_gate import evaluate

result = evaluate(use_sheets=False)
assert result["status"] == "BLOCKED"
assert result["would_post"] is False
print("PASS test_scheduled_publish_activation_gate.py")
