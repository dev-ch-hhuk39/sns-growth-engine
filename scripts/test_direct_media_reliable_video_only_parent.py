#!/usr/bin/env python3
"""Reliable direct-media selection accepts only complete video parents."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import ingest_direct_reference_media_reliable as reliable  # noqa: E402


class Worksheet:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows

    def get_all_records(self) -> list[dict[str, str]]:
        return [dict(row) for row in self.rows]


class Client:
    def __init__(self) -> None:
        self.rows = {
            "source_posts": [
                {
                    "source_post_id": post_id,
                    "source_id": f"source_{post_id}",
                    "target_account_id": "night_scout",
                    "platform": "threads",
                }
                for post_id in ("image", "mixed", "video")
            ],
            "source_post_media": [
                media("image", 0, "image"),
                media("mixed", 0, "video"),
                media("mixed", 1, "image"),
                media("video", 0, "video"),
                media("video", 1, "video"),
            ],
        }

    def _ws(self, name: str) -> Worksheet:
        return Worksheet(self.rows[name])


def media(post_id: str, index: int, media_type: str) -> dict[str, str]:
    suffix = "mp4" if media_type == "video" else "jpg"
    return {
        "source_post_media_id": f"media_{post_id}_{index}",
        "source_post_id": post_id,
        "media_index": str(index),
        "media_type": media_type,
        "original_media_url": f"https://cdn.example/{post_id}_{index}.{suffix}",
        "download_status": "PENDING",
        "created_at": f"2026-08-10T00:0{index}:00+00:00",
    }


permissions = [
    {
        "source_id": f"source_{post_id}",
        "permission_status": "approved",
        "rights_status": "approved_creator_clip",
        "allow_download": "true",
        "allow_cloudinary_storage": "true",
        "allow_original_repost": "true",
        "allow_new_caption": "true",
        "revoked": "false",
    }
    for post_id in ("image", "mixed", "video")
]

original_safe_url = reliable.core.safe_https_url
try:
    reliable.core.safe_https_url = lambda _url, stream_url=False: True
    selected = reliable.select_pending_media_id(
        Client(),
        "night_scout",
        permissions=permissions,
    )
finally:
    reliable.core.safe_https_url = original_safe_url

assert selected == "media_video_1", selected
print("PASS test_direct_media_reliable_video_only_parent.py")
