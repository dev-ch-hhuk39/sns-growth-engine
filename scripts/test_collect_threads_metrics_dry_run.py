#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
p = subprocess.run([sys.executable, "scripts/collect_threads_metrics.py", "--result-id", "r1", "--dry-run"], cwd=ROOT, text=True, capture_output=True)
data = json.loads(p.stdout)
checks = [("exit", p.returncode == 0), ("plan", data["status"] == "PLAN_ONLY"), ("snapshot", data["snapshot_count"] == 1)]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
