#!/usr/bin/env python3
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/collect_source_posts.py"
spec=importlib.util.spec_from_file_location("s", SCRIPT); s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
src=[{"source_id":"x","target_account_ids":["night_scout"],"source_platform":"x","fetch_enabled":True}]
sel,skip=s.select_sources(src, account_id="night_scout", platform="all")
sel2,_=s.select_sources(src, account_id="night_scout", platform="all", include_x=True)
checks=[("x skipped", len(sel)==0 and skip[0]["reason"]=="x_disabled_by_default"), ("x explicit", len(sel2)==1)]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
