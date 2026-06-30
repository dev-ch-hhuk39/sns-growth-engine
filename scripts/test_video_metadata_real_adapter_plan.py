#!/usr/bin/env python3
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/collect_video_references.py"
spec=importlib.util.spec_from_file_location("v", SCRIPT); v=importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
r=v.build_video_reference("https://www.youtube.com/watch?v=x","night_scout",{"ok":True,"title":"T","thumbnail_url":"I","author_handle":"A"})
checks=[("fetched", r["metadata_status"]=="FETCHED"), ("no download", r["can_download"] is False), ("title", r["title"]=="T")]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
