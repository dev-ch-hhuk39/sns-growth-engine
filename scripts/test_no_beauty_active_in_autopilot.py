#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from auto_approve_queue import ALLOWED_ACCOUNTS  # noqa: E402

p = subprocess.run(
    [sys.executable, "scripts/run_autopilot_loop.py", "--dry-run", "--account-id", "beauty_account"],
    cwd=ROOT,
    text=True,
    stdout=subprocess.PIPE,
)
checks = {
    "beauty managed dry-run executes": p.returncode == 0,
    "beauty remains excluded from automatic READY promotion": "beauty_account" not in ALLOWED_ACCOUNTS,
}
for name, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {sum(checks.values())} / FAIL: {len(checks) - sum(checks.values())}")
raise SystemExit(0 if all(checks.values()) else 1)
