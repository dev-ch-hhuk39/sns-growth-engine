#!/usr/bin/env python3
"""Activation command must be safe and non-mutating in plan mode."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/autonomous_mode.json"

before = CONFIG.read_bytes()

result = subprocess.run(
    [
        sys.executable,
        "scripts/activate_scheduled_publish.py",
    ],
    cwd=ROOT,
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
)

after = CONFIG.read_bytes()

assert result.returncode == 0, (
    result.stdout,
    result.stderr,
)

payload = json.loads(result.stdout)

assert payload["status"] == "PLAN_ONLY"
assert payload["would_post"] is False
assert payload["gate"]["status"] == "BLOCKED"
assert payload["gate"]["SCHEDULED_PUBLISH"] == "OFF"
assert (
    "production_evidence_source_not_live"
    in payload["gate"]["blocked_reasons"]
)
assert before == after

print("PASS test_activate_scheduled_publish.py")
