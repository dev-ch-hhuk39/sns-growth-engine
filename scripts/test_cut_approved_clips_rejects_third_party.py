#!/usr/bin/env python3
import importlib.util, argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/cut_approved_clips.py"
spec=importlib.util.spec_from_file_location("c", SCRIPT); c=importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
args=argparse.Namespace(input_path="a.mp4", rights_status="third_party_reference_only", dry_run=True, cut=True, confirm_cut=True, vertical=False, burn_subtitles=False)
p=c.build_plan(args)
checks=[("blocked", p["status"]=="BLOCKED"), ("reason", "rights_status" in p["blocked_reasons"][0])]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
