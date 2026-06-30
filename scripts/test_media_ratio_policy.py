#!/usr/bin/env python3
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=subprocess.run([sys.executable,"scripts/generate_media_post_queue.py","--dry-run"],cwd=ROOT,text=True,capture_output=True)
d=json.loads(p.stdout)
checks=[("70 text", d["media_ratio_policy"]["text_only"]==0.7), ("30 media", d["media_ratio_policy"]["media"]==0.3), ("no auto ready", d["auto_ready"] is False)]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
