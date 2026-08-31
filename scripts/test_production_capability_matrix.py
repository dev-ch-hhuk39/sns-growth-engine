#!/usr/bin/env python3
"""The completion matrix must be complete and cannot pass without evidence."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_capability_matrix import evaluate  # noqa: E402

config = json.loads((ROOT / "config" / "production_capability_matrix.json").read_text(encoding="utf-8"))
status = json.loads((ROOT / "docs" / "capability-matrix-status.json").read_text(encoding="utf-8"))
assert config["accounts"] == ["night_scout", "liver_manager", "beauty_account"]
assert config["constraints"]["media_slot_text_fallback"] is False
assert config["constraints"]["x_operations"] is False
assert config["constraints"]["beauty_account_operations"] is True
assert config["constraints"]["beauty_cross_account_learning"] is False
assert set(config["production_observation_capabilities"]) == {
    "scheduled_publish_streak", "metrics_24_72_168", "pdca_measured_feedback"
}
for account_id in config["accounts"]:
    assert set(status["accounts"][account_id]) == set(config["capabilities"])

assert evaluate()["status"] == "FAIL"
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / "matrix.json"
    complete = json.loads(json.dumps(status))
    for account_id in config["accounts"]:
        for capability in config["capabilities"]:
            evidence = {"verified_at": "fixture", "evidence_type": "live_sheets", "evidence_ref": "fixture"}
            if capability == "scheduled_publish_streak":
                evidence["evidence_type"] = "live_schedule"
                evidence["schedule_runs"] = [{"event_name": "schedule", "run_id": str(index)} for index in range(3)]
            elif capability == "metrics_24_72_168":
                evidence["evidence_type"] = "live_metrics"
                evidence["metric_windows"] = {str(window): {"status": "MEASURED"} for window in (24, 72, 168)}
            elif capability == "pdca_measured_feedback":
                evidence["evidence_type"] = "live_metrics"
                evidence["metric_input_refs"] = ["metric-1"]
            complete["accounts"][account_id][capability] = {"state": "PASS", "evidence": evidence}
    path.write_text(json.dumps(complete), encoding="utf-8")
    assert evaluate(status_path=path)["status"] == "PASS"

    complete["accounts"]["beauty_account"]["scheduled_publish_streak"]["evidence"]["schedule_runs"][0]["event_name"] = "workflow_dispatch"
    path.write_text(json.dumps(complete), encoding="utf-8")
    assert evaluate(status_path=path)["status"] == "FAIL"
    assert evaluate(status_path=path)["development_acceptance"] == "PASS"
    assert evaluate(status_path=path)["production_observation"] == "IN_PROGRESS"

print("PASS test_production_capability_matrix.py")
