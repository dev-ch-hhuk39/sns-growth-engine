#!/usr/bin/env python3
"""Stored full-source reuse stays bound to current rights and exact provenance."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import download_approved_media as module  # noqa: E402

HASH = "a" * 64
VIDEO_URL = "https://www.tiktok.com/@me02_lsm/video/7575822167120694549"
POST_ID = "sp_src_lm_tt_user_002_7575822167120694549"
MEDIA_ID = f"spm_{POST_ID}_0"
ASSET_ID = "ma_source_full_001"
STORAGE_URL = "https://res.cloudinary.com/example/video/upload/source.mp4"

VIDEO = {
    "source_video_id": "sv_src_lm_tt_user_002_7575822167120694549",
    "source_id": "src_lm_tt_user_002", "account_id": "liver_manager", "platform": "tiktok",
    "canonical_video_url": VIDEO_URL, "author_handle": "7366767887526528001",
    "duration_seconds": "69", "content_hash": HASH,
    "rights_status": "approved_creator_clip", "permission_status": "approved",
}
REGISTERED = {
    "source_id": "src_lm_tt_user_002", "source_platform": "tiktok", "platform": "tiktok",
    "canonical_url": "https://www.tiktok.com/@me02_lsm", "source_url": "https://www.tiktok.com/@me02_lsm",
    "source_handle": "@me02_lsm", "target_account_ids": ["liver_manager"], "active": True,
    "rights_status": "approved_creator_clip", "reuse_policy": "approved_creator_clip",
    "media_usage_mode": "direct_and_clip", "media_pipeline_eligible": True, "clip_enabled": True,
}
PERMISSION = {
    "source_id": "src_lm_tt_user_002", "source_handle": "@me02_lsm", "account_id": "liver_manager",
    "allowed_accounts": "liver_manager", "rights_status": "approved_creator_clip", "permission_status": "approved",
    "revoked": "false", "evidence_type": "owner_attestation", "evidence_reference": "existing-owner-scope",
    "approved_by": "user", "approved_at": "2026-08-11T00:00:00+09:00", "expires_at": "",
    **{flag: True for flag in module.CLIP_PERMISSION_FLAGS},
}
POST = {
    "source_post_id": POST_ID, "source_id": "src_lm_tt_user_002", "target_account_id": "liver_manager",
    "canonical_post_url": VIDEO_URL, "external_post_id": "7575822167120694549", "author_handle": "me02_lsm",
    "media_count": "1", "rights_status": "approved_creator_clip", "permission_status": "approved",
}
MEDIA = {
    "source_post_media_id": MEDIA_ID, "source_post_id": POST_ID, "media_index": "0", "media_type": "video",
    "canonical_post_url": VIDEO_URL, "original_media_url": VIDEO_URL, "resolver_backend": "tiktok_public_embed",
    "duration_seconds": "69", "content_hash": HASH, "storage_url": STORAGE_URL,
    "cloudinary_status": "UPLOADED", "cloudinary_public_id": "source", "media_asset_id": ASSET_ID,
    "rights_status": "approved_creator_clip", "permission_status": "approved", "media_role": "full_source",
}
ASSET = {
    "media_id": ASSET_ID, "account_id": "liver_manager", "reference_post_id": POST_ID,
    "source_post_url": VIDEO_URL, "media_type": "video", "duration_seconds": "69",
    "storage_url": STORAGE_URL, "cloudinary_public_id": "source", "upload_status": "UPLOADED",
    "rights_status": "approved_creator_clip", "permission_status": "approved", "content_hash": HASH,
}


def select(video=VIDEO, post=POST, media=MEDIA, asset=ASSET, permissions=None, registered=REGISTERED):
    return module.select_stored_full_source(
        video, [post], [media], [asset], permissions or [PERMISSION], registered,
    )


assert select()["allowed"]
assert not select(media={**MEDIA, "canonical_post_url": "https://www.tiktok.com/@other/video/7575822167120694549"})["allowed"]
assert not select(post={**POST, "author_handle": "someone_else"})["allowed"]
assert not select(media={**MEDIA, "content_hash": "b" * 64})["allowed"]
assert not select(asset={**ASSET, "storage_url": "https://example.invalid/video.mp4"})["allowed"]
assert not select(permissions=[{**PERMISSION, "allow_cut": False}])["allowed"]
assert not select(permissions=[{**PERMISSION, "revoked": True}])["allowed"]
assert not select(registered={**REGISTERED, "source_handle": "@wrong"})["allowed"]

original = os.environ.get("ALLOW_VIDEO_DOWNLOAD")
try:
    os.environ["ALLOW_VIDEO_DOWNLOAD"] = "true"
    args = type("Args", (), {
        "source_video_id": VIDEO["source_video_id"], "source_video_row": VIDEO, "source_url": "",
        "rights_status": VIDEO["rights_status"], "download": True, "confirm_download": True,
        "stored_source_only": True, "source_post_row": POST, "source_media_row": MEDIA,
        "media_assets_rows": [ASSET], "media_permissions_rows": [PERMISSION],
        "registered_source_row": REGISTERED,
    })()
    plan = module.build_download_plan(args)
    assert plan["status"] == "READY", plan
    assert plan["source_url"] == STORAGE_URL
    bad = SimpleNamespace(
        source_video_id=VIDEO["source_video_id"], source_video_row=VIDEO, source_url="",
        rights_status=VIDEO["rights_status"], download=True, confirm_download=True,
        stored_source_only=True, source_post_row=POST, source_media_row=MEDIA,
        media_assets_rows=[{**ASSET, "content_hash": "b" * 64}],
        media_permissions_rows=[PERMISSION], registered_source_row=REGISTERED,
    )
    bad_plan = module.build_download_plan(bad)
    assert bad_plan["status"] == "BLOCKED"
finally:
    if original is None:
        os.environ.pop("ALLOW_VIDEO_DOWNLOAD", None)
    else:
        os.environ["ALLOW_VIDEO_DOWNLOAD"] = original

print("PASS test_download_approved_media_stored_source.py")
