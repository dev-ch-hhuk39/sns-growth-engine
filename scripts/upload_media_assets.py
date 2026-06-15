#!/usr/bin/env python3
"""Plan Cloudinary uploads; real upload requires env and --confirm-upload."""
from __future__ import annotations

import argparse
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))

from media.cloudinary_uploader import plan_cloudinary_uploads


def main() -> int:
    parser = argparse.ArgumentParser(description="upload media assets")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--confirm-upload", action="store_true")
    args = parser.parse_args()

    assets = [{
        "media_asset_id": "mock_media_asset_001",
        "account_id": args.account_id,
        "local_path": "clips/mock.mp4",
        "status": "WAITING_REVIEW",
    }]
    result = plan_cloudinary_uploads(
        assets,
        upload=args.upload,
        confirm_upload=args.confirm_upload,
        dry_run=args.dry_run,
    )
    print(f"[upload_media_assets] account={args.account_id} status={result['status']}")
    print(f"  dry_run={args.dry_run} upload={args.upload} confirm_upload={args.confirm_upload}")
    print(f"  ALLOW_CLOUDINARY_UPLOAD={os.environ.get('ALLOW_CLOUDINARY_UPLOAD', '').lower() == 'true'}")
    for reason in result.get("blocked_reasons", [])[:8]:
        print(f"  [BLOCKED] {reason}")
    print("  実uploadは実行していません")
    if args.upload and not args.confirm_upload:
        return 1
    return 0 if result["status"] in {"DRY_RUN", "BLOCKED", "READY"} else 1


if __name__ == "__main__":
    sys.exit(main())
