#!/usr/bin/env python3
import importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/archive_reference_data.py"
spec=importlib.util.spec_from_file_location("a", SCRIPT); a=importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
p=a.build_archive_payload("raw_post_json", {"token":"abc","nested":{"cookie":"xyz","ok":1}})
checks=[("token redacted", p["payload"]["token"]=="[REDACTED]"), ("cookie redacted", p["payload"]["nested"]["cookie"]=="[REDACTED]"), ("media false", p["third_party_media_saved"] is False)]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
