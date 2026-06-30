#!/usr/bin/env python3
import importlib.util, argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/upload_media_assets.py"
spec=importlib.util.spec_from_file_location("u", SCRIPT); u=importlib.util.module_from_spec(spec); spec.loader.exec_module(u)
args=argparse.Namespace(upload=True, confirm_upload=True, dry_run=True)
p=u.build_upload_plan(args,[{"rights_status":"third_party_reference_only"}])
checks=[("blocked", p["status"]=="BLOCKED"), ("third party", p["third_party_count"]==1)]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
