#!/usr/bin/env python3
"""Unknown and partial metrics must not drive the production PDCA input."""
from metrics_pdca_contract import measured_results_only, pdca_input_summary
from pathlib import Path

rows = [
    {"result_id": "a", "account_id": "night_scout", "platform": "threads", "metrics_status": "MEASURED", "views": 0, "likes": 0},
    {"result_id": "b", "account_id": "night_scout", "platform": "threads", "metrics_status": "PARTIAL", "views": 12, "likes": None},
    {"result_id": "c", "account_id": "night_scout", "platform": "threads", "metrics_status": "UNAVAILABLE", "views": None},
    {"result_id": "d", "account_id": "liver_manager", "platform": "threads", "metrics_status": "MEASURED", "views": 8},
]
selected = measured_results_only(rows, account_id="night_scout", platform="threads")
assert [row["result_id"] for row in selected] == ["a"]
assert selected[0]["views"] == 0 and selected[0]["likes"] == 0
summary = pdca_input_summary(selected)
assert summary["metrics_status"] == "MEASURED_ONLY"
assert summary["known_metric_value_count"] == 2
assert pdca_input_summary([])["metrics_status"] == "NO_MEASURED_RESULTS"
runner = (Path(__file__).resolve().parent / "run_pdca_cycle.py").read_text(encoding="utf-8")
assert '"--no-dry-run"' in runner
assert "--no-dry-run --apply --confirm-pdca" in runner
print("PASS test_metrics_pdca_contract.py")
