#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
result = subprocess.run(
    [sys.executable, "scripts/prepare_pilot_sources.py", "--account-id", "all", "--max-per-account", "1", "--apply"],
    cwd=ROOT,
    text=True,
    capture_output=True,
)
checks = [("blocked exit", result.returncode == 1), ("confirm required", "--confirm-pilot" in result.stdout)]
bad = [n for n, ok in checks if not ok]
for n, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
