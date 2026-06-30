#!/usr/bin/env python3
import importlib.util, argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/generate_clip_candidates.py"
spec=importlib.util.spec_from_file_location("g", SCRIPT); g=importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
args=argparse.Namespace(account_id="night_scout", limit=1, n_candidates=1, transcript_status="done", apply=False, confirm_generate=False, cut=False)
p=g.build_plan(args)
checks=[("plan only", p["status"]=="PLAN_ONLY"), ("rights default", p["candidate_fields"]["rights_status"]=="third_party_reference_only by default"), ("not cuttable", p["safety"]["third_party_reference_only_cuttable"] is False)]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
