#!/usr/bin/env python3
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/generate_media_post_queue.py"
spec=importlib.util.spec_from_file_location("m", SCRIPT); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
r=m.build_queue_row({"media_asset_id":"a","account_id":"night_scout","status":"APPROVED","rights_status":"owned"})
checks=[("row", r is not None), ("waiting", r["status"]=="WAITING_REVIEW"), ("auto false", r["auto_publish"]=="false")]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
