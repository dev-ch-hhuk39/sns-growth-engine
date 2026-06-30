#!/usr/bin/env python3
from pathlib import Path
src=(Path(__file__).resolve().parents[1]/"scripts/run_growth_loop.py").read_text(encoding="utf-8")
checks=[("kill switch reported", "kill_switch_respected" in src), ("confirm required", "--confirm-run" in src), ("apply blocked", "--apply requires --confirm-run" in src)]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
