#!/usr/bin/env python3
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
acceptance = json.loads((root / "config/goal_acceptance.json").read_text(encoding="utf-8"))
criteria = {row["id"]: row for row in acceptance["criteria"]}
observation_ids = {
    "three_account_scheduled_publish_streak",
    "three_account_metrics_24_72_168",
    "three_account_pdca_measured_feedback",
}
for criterion_id in observation_ids:
    row = criteria[criterion_id]
    assert row["acceptance_layer"] == "production_observation"
    assert row["blocks_development_completion"] is False

goal = (root / "GOAL.md").read_text(encoding="utf-8")
assert "development_acceptance=PASS" in goal
assert "production_observation=IN_PROGRESS" in goal
print("PASS test_acceptance_layers.py")
