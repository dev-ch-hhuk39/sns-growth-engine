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
assert config["accounts"] == ["night_scout", "liver_manager"]
assert config["constraints"]["media_slot_text_fallback"] is False
assert config["constraints"]["x_operations"] is False
assert config["constraints"]["beauty_account_operations"] is False
for account_id in config["accounts"]:
    assert set(status["accounts"][account_id]) == set(config["capabilities"])

assert evaluate()["status"] == "FAIL"
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / "matrix.json"
    complete = json.loads(json.dumps(status))
    for account_id in config["accounts"]:
        for capability in config["capabilities"]:
            complete["accounts"][account_id][capability] = {"state": "PASS", "evidence": {key: "fixture" for key in config["required_evidence"]}}
    path.write_text(json.dumps(complete), encoding="utf-8")
    assert evaluate(status_path=path)["status"] == "PASS"

print("PASS test_production_capability_matrix.py")
