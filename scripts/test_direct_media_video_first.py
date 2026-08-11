#!/usr/bin/env python3
"""Direct reference media is video-only when image fallback is disabled."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import run_direct_reference_media_pipeline as pipeline


def source(source_id: str, priority: str) -> dict:
    return {
        "source_id": source_id,
        "priority": priority,
        "media_usage_mode": "direct_media_reuse",
    }


def permission(source_id: str) -> dict:
    return {
        "source_id": source_id,
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "usage_mode": "direct_media_reuse",
        "allow_download": "true",
        "allow_cloudinary_storage": "true",
        "allow_original_repost": "true",
        "allow_new_caption": "true",
        "revoked": "false",
        "evidence_type": "owner_attestation",
        "evidence_reference": "fixture",
        "approved_by": "owner",
        "approved_at": "2026-08-10T00:00:00+00:00",
    }


def post(
    post_id: str,
    source_id: str,
) -> dict:
    return {
        "source_post_id": post_id,
        "source_id": source_id,
        "target_account_id": "night_scout",
        "platform": "x",
        "original_post_text": (
            "店選びでは条件だけでなく"
            "客層や相談しやすさも確認する。"
        ),
        "published_at": "2026-08-01T00:00:00+00:00",
    }


def media(
    post_id: str,
    media_type: str,
) -> dict:
    suffix = "mp4" if media_type == "video" else "jpg"

    return {
        "source_post_media_id": f"spm_{post_id}",
        "source_post_id": post_id,
        "media_index": "0",
        "media_type": media_type,
        "original_media_url": (
            f"https://cdn.example/{post_id}.{suffix}"
        ),
        "cloudinary_status": "UPLOADED",
        "storage_url": (
            f"https://res.cloudinary.com/demo/"
            f"{post_id}.{suffix}"
        ),
    }


def asset(
    post_id: str,
    media_type: str,
) -> dict:
    suffix = "mp4" if media_type == "video" else "jpg"

    return {
        "media_id": f"asset_{post_id}",
        "media_asset_id": f"asset_{post_id}",
        "reference_post_id": post_id,
        "media_type": media_type,
        "original_media_url": (
            f"https://cdn.example/{post_id}.{suffix}"
        ),
        "cloudinary_status": "UPLOADED",
        "storage_url": (
            f"https://res.cloudinary.com/demo/"
            f"{post_id}.{suffix}"
        ),
        "reuse_status": "APPROVED",
    }


def understanding(post_id: str) -> dict:
    return {
        "understanding_id": f"understanding_{post_id}",
        "source_post_media_id": f"spm_{post_id}",
        "status": "PASS",
    }


tables = {
    "source_posts": [
        post("image_post", "source_image"),
        post("video_post", "source_video"),
    ],
    "source_accounts": [
        source("source_image", "100"),
        source("source_video", "1"),
    ],
    "reference_sources": [],
    "media_permissions": [
        permission("source_image"),
        permission("source_video"),
    ],
    "posted_results": [],
    "queue": [],
    "media_assets": [
        asset("image_post", "image"),
        asset("video_post", "video"),
    ],
    "source_post_media": [
        media("image_post", "image"),
        media("video_post", "video"),
    ],
    "source_media_understanding": [
        understanding("image_post"),
        understanding("video_post"),
    ],
}

original_records = pipeline._records
original_load = pipeline._load

try:
    pipeline._records = (
        lambda _client, logical: [
            dict(row)
            for row in tables.get(logical, [])
        ]
    )

    pipeline._load = (
        lambda _path: {
            "direct_media_preferred_type": "video",
        "direct_media_image_fallback_enabled": False,
        }
    )

    candidates, _reasons = (
        pipeline.select_direct_candidates(
            object(),
            "night_scout",
        )
    )

    selected_ids = [
        candidate[0]["source_post_id"]
        for candidate in candidates
    ]

    assert selected_ids == ["video_post"], selected_ids

    tables["source_posts"] = [
        post("image_post", "source_image"),
    ]
    tables["source_accounts"] = [
        source("source_image", "100"),
    ]
    tables["media_permissions"] = [
        permission("source_image"),
    ]
    tables["media_assets"] = [
        asset("image_post", "image"),
    ]
    tables["source_post_media"] = [
        media("image_post", "image"),
    ]
    tables["source_media_understanding"] = [
        understanding("image_post"),
    ]

    fallback_candidates, _reasons = (
        pipeline.select_direct_candidates(
            object(),
            "night_scout",
        )
    )

    assert fallback_candidates == []

finally:
    pipeline._records = original_records
    pipeline._load = original_load

print(
    "PASS test_direct_media_video_first.py"
)
