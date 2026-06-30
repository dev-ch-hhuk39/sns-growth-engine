#!/usr/bin/env python3
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/collect_source_posts.py"
spec=importlib.util.spec_from_file_location("s", SCRIPT); s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
sel,skip=s.select_sources([{"source_id":"m","target_account_ids":["night_scout"],"source_platform":"threads","fetch_enabled":True,"manual_only":True}], account_id="night_scout", platform="threads")
checks=[("none selected", len(sel)==0), ("manual skipped", skip[0]["reason"]=="manual_only")]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
