#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=subprocess.run([sys.executable,"scripts/run_growth_loop.py","--dry-run","--account-id","all"],cwd=ROOT,text=True,capture_output=True)
d=json.loads(p.stdout)
checks=[("auto false", d["auto_post"] is False), ("real false", d["real_post"] is False), ("plan", d["status"]=="PLAN_ONLY")]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
