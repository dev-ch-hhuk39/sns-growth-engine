#!/usr/bin/env python3
import argparse, importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("c", ROOT / "scripts/cut_approved_clips.py")
c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
blocked = c.build_plan(argparse.Namespace(input_path="", rights_status="third_party_reference_only", dry_run=True, cut=True, confirm_cut=True, vertical=False, burn_subtitles=False))
plan = c.build_plan(argparse.Namespace(input_path="", rights_status="owned", dry_run=True, cut=False, confirm_cut=False, vertical=False, burn_subtitles=False))
checks = [
    ("third party blocked", blocked["status"] == "BLOCKED"),
    ("rights reason", any("reference-only" in r for r in blocked["blocked_reasons"])),
    ("plan only no cut", plan["status"] == "PLAN_ONLY"),
    ("adapter status", "ffmpeg_cli" in plan["adapter_status"]),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
