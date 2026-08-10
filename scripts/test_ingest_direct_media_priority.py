#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import ingest_direct_reference_media_reliable as module  # noqa: E402


class FakeWorksheet:
    def __init__(self, rows):
        self.rows = list(rows)

    def get_all_records(self):
        return [
            dict(row)
            for row in self.rows
        ]


class FakeClient:
    def __init__(self, posts, media):
        self.tabs = {
            "source_posts": FakeWorksheet(posts),
            "source_post_media": FakeWorksheet(media),
        }

    def _ws(self, logical):
        return self.tabs[logical]


def permission(source_id):
    return {
        "source_id": source_id,
        "updated_at": "2026-08-01T00:00:00+00:00",
        "permission_status": "approved",
        "rights_status": "approved_creator_clip",
        "allow_download": "true",
        "allow_cloudinary_storage": "true",
        "allow_original_repost": "true",
        "allow_new_caption": "true",
        "revoked": "false",
    }


posts = [
    {
        "source_post_id": "post-youtube",
        "source_id": "source-youtube",
        "target_account_id": "night_scout",
        "platform": "youtube",
    },
    {
        "source_post_id": "post-tiktok",
        "source_id": "source-tiktok",
        "target_account_id": "night_scout",
        "platform": "tiktok",
    },
    {
        "source_post_id": "post-threads",
        "source_id": "source-threads",
        "target_account_id": "night_scout",
        "platform": "threads",
    },
    {
        "source_post_id": "post-profile",
        "source_id": "source-threads",
        "target_account_id": "night_scout",
        "platform": "threads",
    },
]

media = [
    {
        "source_post_media_id": "media-youtube",
        "source_post_id": "post-youtube",
        "media_type": "video",
        "original_media_url": (
            "https://www.youtube.com/watch?v=abc"
        ),
        "download_status": (
            "SKIPPED_EXTERNAL_UNAVAILABLE"
        ),
        "created_at": (
            "2026-08-01T04:00:00+00:00"
        ),
    },
    {
        "source_post_media_id": "media-tiktok",
        "source_post_id": "post-tiktok",
        "media_type": "video",
        "original_media_url": (
            "https://www.tiktok.com/@sample/video/123"
        ),
        "download_status": "PENDING",
        "created_at": (
            "2026-08-01T03:00:00+00:00"
        ),
    },
    {
        "source_post_media_id": "media-threads",
        "source_post_id": "post-threads",
        "media_type": "video",
        "original_media_url": (
            "https://scontent.example.cdninstagram.com/"
            "v/t51.82787-15/post.jpg"
        ),
        "download_status": "PENDING",
        "created_at": (
            "2026-08-01T02:00:00+00:00"
        ),
    },
    {
        "source_post_media_id": "media-profile",
        "source_post_id": "post-profile",
        "media_type": "video",
        "original_media_url": (
            "https://scontent.example.cdninstagram.com/"
            "v/t51.82787-19/profile.jpg"
        ),
        "download_status": "PENDING",
        "created_at": (
            "2026-08-01T05:00:00+00:00"
        ),
    },
]

permissions = [
    permission("source-youtube"),
    permission("source-tiktok"),
    permission("source-threads"),
]

original_safe_url = module.core.safe_https_url

try:
    module.core.safe_https_url = (
        lambda _url, stream_url=False: True
    )

    client = FakeClient(
        posts,
        media,
    )

    selected = module.select_pending_media_id(
        client,
        "night_scout",
        permissions=permissions,
    )

    assert selected == "media-threads"

    without_threads = FakeClient(
        posts,
        [
            row
            for row in media
            if row["source_post_media_id"]
            not in {
                "media-threads",
                "media-profile",
            }
        ],
    )

    selected = module.select_pending_media_id(
        without_threads,
        "night_scout",
        permissions=permissions,
    )

    assert selected == "media-tiktok"

    recoverable_threads = FakeClient(
        posts,
        [
            {
                **next(
                    row
                    for row in media
                    if row[
                        "source_post_media_id"
                    ]
                    == "media-threads"
                ),
                "download_status": "FAILED",
                "last_error": (
                    "ingest_failed:RuntimeError"
                ),
                "understanding_status": "PASS",
                "understanding_id": (
                    "smu-media-threads"
                ),
            }
        ],
    )

    selected = module.select_pending_media_id(
        recoverable_threads,
        "night_scout",
        permissions=permissions,
    )

    assert selected == "media-threads"

finally:
    module.core.safe_https_url = (
        original_safe_url
    )

print(
    "PASS "
    "test_ingest_direct_media_priority.py"
)
