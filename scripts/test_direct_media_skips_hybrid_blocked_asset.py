#!/usr/bin/env python3
"""A Hybrid-blocked Direct asset must not starve later candidates."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import run_direct_reference_media_pipeline as pipeline  # noqa: E402


def source(source_id: str) -> dict[str, str]:
    return {"source_id": source_id, "platform": "tiktok", "priority": "1"}


def permission(source_id: str) -> dict[str, str]:
    return {
        "source_id": source_id,
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "usage_mode": "direct_media_reuse",
        "allow_download": "true",
        "allow_cloudinary_storage": "true",
        "allow_original_repost": "true",
        "allow_new_caption": "true",
        "evidence_type": "owner_attestation",
        "evidence_reference": "fixture",
        "approved_by": "owner",
        "approved_at": "2026-08-25T00:00:00+00:00",
        "revoked": "false",
    }


def post(post_id: str, source_id: str) -> dict[str, str]:
    return {
        "source_post_id": post_id,
        "source_id": source_id,
        "target_account_id": "liver_manager",
        "platform": "tiktok",
        "canonical_post_url": f"https://www.tiktok.com/@owner/video/{post_id}",
        "original_post_text": "配信で初見コメントを増やすには、質問と挨拶を置く。",
        "published_at": "2026-08-25T00:00:00+00:00",
    }


def media(post_id: str) -> dict[str, str]:
    return {
        "source_post_media_id": f"spm_{post_id}",
        "source_post_id": post_id,
        "media_index": "0",
        "media_type": "video",
        "original_media_url": f"https://cdn.example/{post_id}.mp4",
        "cloudinary_status": "UPLOADED",
        "storage_url": f"https://res.cloudinary.com/demo/{post_id}.mp4",
        "duration_seconds": "20",
    }


def asset(post_id: str) -> dict[str, str]:
    return {
        "media_asset_id": f"asset_{post_id}",
        "media_id": f"asset_{post_id}",
        "reference_post_id": post_id,
        "media_type": "video",
        "original_media_url": f"https://cdn.example/{post_id}.mp4",
        "cloudinary_status": "UPLOADED",
        "storage_url": f"https://res.cloudinary.com/demo/{post_id}.mp4",
    }


tables = {
    "source_posts": [post("blocked", "src_blocked"), post("next", "src_next")],
    "source_accounts": [source("src_blocked"), source("src_next")],
    "reference_sources": [],
    "media_permissions": [permission("src_blocked"), permission("src_next")],
    "posted_results": [],
    "queue": [{
        "queue_id": "q_blocked",
        "account_id": "liver_manager",
        "generation_mode": "direct_reference_media",
        "media_asset_id": "asset_blocked",
        "status": "WAITING_REVIEW",
        "validator_status": "BLOCKED",
    }],
    "media_assets": [asset("blocked"), asset("next")],
    "source_post_media": [media("blocked"), media("next")],
    "source_media_understanding": [
        {"source_post_media_id": "spm_blocked", "status": "PASS"},
        {"source_post_media_id": "spm_next", "status": "PASS"},
    ],
}

original_records = pipeline._records
try:
    pipeline._records = lambda _client, logical: [dict(row) for row in tables.get(logical, [])]
    candidates, _reasons = pipeline.select_direct_candidates(object(), "liver_manager")
finally:
    pipeline._records = original_records

assert [row[0]["source_post_id"] for row in candidates] == ["next"]
print("PASS test_direct_media_skips_hybrid_blocked_asset.py")
