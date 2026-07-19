#!/usr/bin/env python3
"""Source research dry-run is bounded and side-effect free."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
run = subprocess.run(
    [sys.executable, "scripts/run_source_research.py", "--account-id", "all", "--dry-run"],
    cwd=ROOT,
    text=True,
    capture_output=True,
    check=False,
)
assert run.returncode == 0, run.stderr
result = json.loads(run.stdout)
assert result["status"] == "PLAN_ONLY", result
assert 0 < result["selected_query_count"] <= 2, result
assert result["would_publish"] is False, result
assert result["would_download"] is False, result
assert result["agent_reach_doctor"]["status"] == "PLANNED", result
print("PASS test_source_research_dry_run.py")
