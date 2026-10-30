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
        "source_handle": {"source-x": "approved", "source-youtube": "youtube_owner", "source-tiktok": "sample", "source-threads": "approved"}[source_id],
        "account_id": "night_scout",
        "allowed_accounts": ["night_scout"],
        "updated_at": "2026-08-01T00:00:00+00:00",
        "permission_status": "approved",
        "rights_status": "approved_creator_clip",
        "allow_download": "true",
        "allow_cloudinary_storage": "true",
        "allow_original_repost": "true",
        "allow_new_caption": "true",
        "evidence_type": "contract",
        "evidence_reference": "fixture",
        "approved_by": "owner",
        "approved_at": "2026-08-01T00:00:00+00:00",
        "revoked": "false",
    }


posts = [
    {
        "source_post_id": "post-x",
        "source_id": "source-x",
        "target_account_id": "night_scout",
        "author_handle": "approved",
        "platform": "x",
        "original_post_text": "夜職の店選びでは、時給やノルマだけでなく担当へ相談できる環境も確認することが大事です。",
    },
    {
        "source_post_id": "post-youtube",
        "source_id": "source-youtube",
        "target_account_id": "night_scout",
        "author_handle": "youtube_owner",
        "platform": "youtube",
        "original_post_text": "夜職の店選びでは、時給やノルマだけでなく担当へ相談できる環境も確認することが大事です。",
    },
    {
        "source_post_id": "post-tiktok",
        "source_id": "source-tiktok",
        "target_account_id": "night_scout",
        "author_handle": "sample",
        "platform": "tiktok",
        "original_post_text": "夜職の店選びでは、時給やノルマだけでなく担当へ相談できる環境も確認することが大事です。",
    },
    {
        "source_post_id": "post-threads",
        "source_id": "source-threads",
        "target_account_id": "night_scout",
        "author_handle": "approved",
        "platform": "threads",
        "original_post_text": "夜職の店選びでは、時給やノルマだけでなく担当へ相談できる環境も確認することが大事です。",
    },
    {
        "source_post_id": "post-profile",
        "source_id": "source-threads",
        "target_account_id": "night_scout",
        "author_handle": "approved",
        "platform": "threads",
        "original_post_text": "夜職の店選びでは、時給やノルマだけでなく担当へ相談できる環境も確認することが大事です。",
    },
]

media = [
    {
        "source_post_media_id": "media-x",
        "source_post_id": "post-x",
        "media_type": "video",
        "original_media_url": "https://x.com/approved/status/456",
        "download_status": "PENDING",
        "created_at": "2026-08-01T05:00:00+00:00",
    },
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
        "canonical_post_url": "https://www.threads.com/@approved/post/ABC123",
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
        "canonical_post_url": "https://www.threads.com/@approved",
        "download_status": "PENDING",
        "created_at": (
            "2026-08-01T05:00:00+00:00"
        ),
    },
]

permissions = [
    permission("source-x"),
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

    assert selected == "media-x"

    without_threads = FakeClient(
        posts,
        [
            row
            for row in media
            if row["source_post_media_id"]
            not in {
                "media-x",
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

    assert selected == ""  # Neither deferred platform can replace unavailable YouTube.
    pending_youtube = [
        {**row, "download_status": "PENDING"}
        if row["source_post_media_id"] == "media-youtube" else row
        for row in without_threads.tabs["source_post_media"].rows
    ]
    assert module.select_pending_media_id(
        FakeClient(posts, pending_youtube), "night_scout", permissions=permissions,
    ) == "media-youtube"

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

    assert selected == ""  # Recoverable legacy state does not override owner deferral.
    legacy_posts = [{**post, "target_account_id": "beauty_account"} for post in posts]
    legacy_permissions = [{**row, "account_id": "beauty_account", "allowed_accounts": ["beauty_account"]}
                          for row in permissions]
    assert module.select_pending_media_id(
        FakeClient(legacy_posts, recoverable_threads.tabs["source_post_media"].rows),
        "beauty_account", permissions=legacy_permissions,
    ) == "media-threads"

finally:
    module.core.safe_https_url = (
        original_safe_url
    )

print(
    "PASS "
    "test_ingest_direct_media_priority.py"
)
