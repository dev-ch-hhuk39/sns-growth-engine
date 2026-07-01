#!/usr/bin/env python3
import importlib.util
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("upload", ROOT / "scripts/upload_media_assets.py")
upload = importlib.util.module_from_spec(spec); spec.loader.exec_module(upload)
args = argparse.Namespace(upload=False, confirm_upload=False, dry_run=True)
plan = upload.build_upload_plan(args, [{"media_asset_id": "m", "rights_status": "third_party_reference_only", "status": "APPROVED"}])
checks = [("blocked", plan["status"] == "BLOCKED"), ("count", plan["third_party_count"] == 1)]
bad = [n for n, ok in checks if not ok]
for n, ok in checks: print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
