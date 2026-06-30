#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = subprocess.run([sys.executable, "scripts/run_growth_loop.py", "--dry-run", "--account-id", "all"], cwd=ROOT, text=True, capture_output=True)
d = json.loads(p.stdout)
checks = [
    ("plan", d["status"] == "PLAN_ONLY"),
    ("adapter status", "adapter_status" in d),
    ("metrics adapter", "metrics" in d["adapter_status"]),
    ("source adapter", "source" in d["adapter_status"]),
    ("video adapter", "video" in d["adapter_status"]),
    ("autopost off", d["adapter_status"]["autopost"] == "off" and d["auto_post"] is False),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
