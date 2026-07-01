#!/usr/bin/env python3
import importlib.util
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ingest", ROOT / "scripts/ingest_media_assets.py")
ingest = importlib.util.module_from_spec(spec); spec.loader.exec_module(ingest)
args = argparse.Namespace(source_url="https://www.youtube.com/watch?v=x", local_file="", platform="youtube", rights_status="third_party_reference_only", account_id="night_scout", dry_run=True, apply=False)
plan = ingest.build_ingest_plan(args)
checks = [("blocked", plan["status"] == "BLOCKED"), ("no download", plan["media_download"] is False), ("has reason", bool(plan["blocked_reasons"]))]
bad = [n for n, ok in checks if not ok]
for n, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
