#!/usr/bin/env python3
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/collect_source_posts.py"
spec=importlib.util.spec_from_file_location("s", SCRIPT); s=importlib.util.module_from_spec(spec); spec.loader.exec_module(s)
raw=s.redact_raw({"cookie":"abc","token":"def","ok":1})
checks=[("cookie", raw["cookie"]=="[REDACTED]"), ("token", raw["token"]=="[REDACTED]"), ("ok", raw["ok"]==1)]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
