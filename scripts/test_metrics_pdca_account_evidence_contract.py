#!/usr/bin/env python3
"""Measured metrics must be account-scoped and never silently become NO_DATA."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from learning.feature_attribution import build_observations, FEATURE_SCHEMA_VERSION
from run_growth_attribution_cycle import _read_tab

base = {
    "result_id": "same-result-id", "platform": "threads", "status": "POSTED",
    "feature_schema_version": FEATURE_SCHEMA_VERSION, "primary_topic": "topic",
}
posts = [{**base, "account_id": "night_scout"}, {**base, "account_id": "liver_manager"}]
snapshots = [
    {"result_id": "same-result-id", "platform": "threads", "account_id": "night_scout", "metrics_status": "MEASURED", "collection_window_hours": "24", "views": "100"},
    {"result_id": "same-result-id", "platform": "threads", "account_id": "liver_manager", "metrics_status": "PARTIAL", "collection_window_hours": "24", "views": "999"},
]
observations = build_observations(posts, snapshots, account_id="all")
assert len(observations) == 1 and observations[0]["account_id"] == "night_scout", observations
legacy = [{**base, "account_id": "night_scout", "excluded_from_metrics_baseline": "true"}]
assert not build_observations(legacy, snapshots[:1], account_id="night_scout")

class BrokenClient:
    def _ws(self, _logical):
        raise RuntimeError("rate limit")

rows, error = _read_tab(BrokenClient(), "metric_snapshots")
assert rows == [] and error == "metric_snapshots_READ_FAILED:RuntimeError", error

workflow = (ROOT / ".github/workflows/production-autopilot-aftercare.yml").read_text(encoding="utf-8")
assert 'cron: "0 * * * *"' in workflow
assert "fail-fast: false" in workflow and "matrix:" in workflow
assert '--account-id "$ACCOUNT_ID"' in workflow
print("metrics PDCA account evidence contract: PASS")
