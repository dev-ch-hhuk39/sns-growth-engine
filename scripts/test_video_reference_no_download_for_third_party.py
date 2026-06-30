#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=subprocess.run([sys.executable,"scripts/collect_video_references.py","--url","https://youtube.com/watch?v=x","--dry-run"],cwd=ROOT,text=True,capture_output=True)
d=json.loads(p.stdout); row=d["rows"][0]
checks=[("no download", d["download"] is False), ("reference only", row["rights_status"]=="third_party_reference_only"), ("cannot cut", row["can_cut"] is False)]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
