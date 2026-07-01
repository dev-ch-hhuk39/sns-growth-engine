#!/usr/bin/env python3
import importlib.util
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cut", ROOT / "scripts/cut_approved_clips.py")
cut = importlib.util.module_from_spec(spec); spec.loader.exec_module(cut)
args = argparse.Namespace(input_path="a.mp4", rights_status="third_party_reference_only", dry_run=True, cut=True, confirm_cut=True, vertical=False, burn_subtitles=False)
plan = cut.build_plan(args)
checks = [("blocked", plan["status"] == "BLOCKED"), ("no cut", plan["ffmpeg_cut"] is False), ("reason", bool(plan["blocked_reasons"]))]
bad = [n for n, ok in checks if not ok]
for n, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
