#!/usr/bin/env python3
from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/generate_video_reference_posts.py"
spec=importlib.util.spec_from_file_location("v", SCRIPT); v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
rows=v.build_video_posts({"title":"sample","video_url":"u"},"night_scout",limit=5)
checks=[("five", len(rows)==5), ("waiting", all(r["status"]=="WAITING_REVIEW" for r in rows)), ("no media", all(r["media_strategy"]=="none" for r in rows))]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
