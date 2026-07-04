#!/usr/bin/env python3
import argparse
from upload_media_assets import build_upload_plan

def main() -> int:
    result = build_upload_plan(argparse.Namespace(upload=False, confirm_upload=False, dry_run=True), [{"media_asset_id": "m", "rights_status": "third_party_reference_only"}])
    ok = result["status"] == "BLOCKED"
    print(f"  {'PASS' if ok else 'FAIL'} upload requires approved rights")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
