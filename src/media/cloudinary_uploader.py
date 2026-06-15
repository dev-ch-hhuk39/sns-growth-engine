"""Cloudinary upload safety wrapper."""
from __future__ import annotations

import os
from typing import Any


def plan_cloudinary_upload(
    media_asset: dict[str, Any],
    *,
    upload: bool = False,
    confirm_upload: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    allow_env = os.environ.get("ALLOW_CLOUDINARY_UPLOAD", "").lower() == "true"
    blocked: list[str] = []
    if upload and not confirm_upload:
        blocked.append("--upload requires --confirm-upload")
    if upload and not allow_env:
        blocked.append("ALLOW_CLOUDINARY_UPLOAD=true is required")
    if media_asset.get("status") in {"WAITING_REVIEW", "BLOCKED"}:
        blocked.append(f"media_asset status={media_asset.get('status')}: upload不可")
    if not upload:
        blocked.append("upload flag not set: plan only")

    return {
        "status": "BLOCKED" if blocked else ("DRY_RUN" if dry_run else "READY"),
        "media_asset_id": media_asset.get("media_asset_id", ""),
        "local_path": media_asset.get("local_path", ""),
        "cloudinary_url": "",
        "dry_run": dry_run,
        "upload": upload,
        "confirm_upload": confirm_upload,
        "allow_cloudinary_upload": allow_env,
        "blocked_reasons": blocked,
    }


def plan_cloudinary_uploads(
    media_assets: list[dict[str, Any]],
    *,
    upload: bool = False,
    confirm_upload: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    plans = [
        plan_cloudinary_upload(asset, upload=upload, confirm_upload=confirm_upload, dry_run=dry_run)
        for asset in media_assets
    ]
    blocked = [r for p in plans for r in p.get("blocked_reasons", [])]
    return {
        "status": "BLOCKED" if blocked else ("DRY_RUN" if dry_run else "READY"),
        "plans": plans,
        "uploaded_count": 0,
        "blocked_reasons": blocked,
    }
