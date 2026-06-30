#!/usr/bin/env python3
import importlib.util, argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; SCRIPT=ROOT/"scripts/transcribe_video_reference.py"
spec=importlib.util.spec_from_file_location("t", SCRIPT); t=importlib.util.module_from_spec(spec); spec.loader.exec_module(t)
args=argparse.Namespace(account_id="night_scout", limit=1, apply=True, confirm_transcribe=True, allow_real_transcription=True)
p=t.build_plan(args, env={"ALLOW_TRANSCRIPTION_API":"false"})
p2=t.build_plan(args, env={"ALLOW_TRANSCRIPTION_API":"true"})
checks=[("blocked api flag absent", "--allow-real-transcription" not in p["delegate_argv"]), ("api allowed when env true", "--allow-real-transcription" in p2["delegate_argv"])]
bad=[n for n,o in checks if not o]
for n,o in checks: print(f"  {'PASS' if o else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
