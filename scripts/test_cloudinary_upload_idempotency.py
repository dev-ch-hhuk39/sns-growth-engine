#!/usr/bin/env python3
"""An uploaded asset is reused without another Cloudinary API call."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from upload_media_assets import build_upload_plan, execute_cloudinary_uploads


args = argparse.Namespace(upload=True, confirm_upload=True, dry_run=False)
asset = {
    "media_asset_id": "asset-idempotent",
    "account_id": "liver_manager",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "upload_status": "UPLOADED",
    "cloudinary_url": "https://res.cloudinary.com/example/video/upload/asset-idempotent.mp4",
    "local_path": "",
}
plan = build_upload_plan(args, [asset])
assert plan["status"] == "ALREADY_UPLOADED", plan
assert plan["already_uploaded_count"] == 1, plan
assert not plan["assets"], plan

# execute_cloudinary_uploads must return immediately for a non-READY plan;
# importing or calling the Cloudinary SDK would change this status.
result = execute_cloudinary_uploads(plan)
assert result["status"] == "ALREADY_UPLOADED", result
assert result["already_uploaded_count"] == 1, result
print("PASS test_cloudinary_upload_idempotency.py")
