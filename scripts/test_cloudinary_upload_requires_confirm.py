#!/usr/bin/env python3
import argparse, importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("u", ROOT / "scripts/upload_media_assets.py")
u = importlib.util.module_from_spec(spec); spec.loader.exec_module(u)
args = argparse.Namespace(upload=True, confirm_upload=False, dry_run=True)
owned = [{"media_asset_id": "m1", "rights_status": "owned", "status": "APPROVED", "local_path": "x"}]
third = [{"media_asset_id": "m2", "rights_status": "third_party_reference_only", "status": "APPROVED", "local_path": "x"}]
r1 = u.build_upload_plan(args, owned)
r2 = u.build_upload_plan(argparse.Namespace(upload=False, confirm_upload=False, dry_run=True), third)
checks = [
    ("confirm required", "--upload requires --confirm-upload" in r1.get("blocked_reasons", [])),
    ("third party blocked", r2["status"] == "BLOCKED"),
    ("adapter status", "cloudinary" in r1.get("adapter_status", {})),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
