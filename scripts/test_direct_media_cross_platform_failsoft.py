#!/usr/bin/env python3
"""Provider-blocked YouTube cannot starve a pending Threads Direct candidate."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import ingest_direct_reference_media_reliable as module  # noqa: E402


class FakeWorksheet:
    def __init__(self, rows):
        self.rows = list(rows)

    def get_all_records(self):
        return [dict(row) for row in self.rows]


class FakeClient:
    def __init__(self, posts, media, understandings=None):
        self.tabs = {
            "source_posts": FakeWorksheet(posts),
            "source_post_media": FakeWorksheet(media),
            "source_media_understanding": FakeWorksheet(understandings or []),
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
        "evidence_type": "contract",
        "evidence_reference": "fixture",
        "approved_by": "owner",
        "approved_at": "2026-08-01T00:00:00+00:00",
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
        "source_post_id": "post-threads",
        "source_id": "source-threads",
        "target_account_id": "night_scout",
        "platform": "threads",
        "canonical_post_url": "https://www.threads.com/@approved/post/ABC123",
    },
]

now = datetime.now(timezone.utc)

media = [
    {
        "source_post_media_id": "media-youtube",
        "source_post_id": "post-youtube",
        "media_type": "video",
        "original_media_url": "https://www.youtube.com/watch?v=abc",
        "download_status": "SKIPPED_EXTERNAL_UNAVAILABLE",
        "updated_at": (now - timedelta(minutes=2)).isoformat(),
        "created_at": "2026-08-25T09:00:00+00:00",
    },
    {
        "source_post_media_id": "media-threads",
        "source_post_id": "post-threads",
        "media_type": "video",
        "original_media_url": (
            "https://scontent.example.cdninstagram.com/"
            "v/t51.82787-15/video.mp4"
        ),
        "canonical_post_url": "https://www.threads.com/@approved/post/ABC123",
        "download_status": "PENDING",
        "created_at": "2026-08-25T08:00:00+00:00",
    },
]

permissions = [
    permission("source-youtube"),
    permission("source-threads"),
]

original_safe_url = module.core.safe_https_url
original_understanding = module.core.media_understanding_needs_refresh
original_env = os.environ.get("ALLOW_LOCAL_TRANSCRIPTION")

try:
    os.environ["ALLOW_LOCAL_TRANSCRIPTION"] = "true"
    module.core.safe_https_url = lambda _url, stream_url=False: True
    module.core.media_understanding_needs_refresh = lambda _media, _understanding: True

    selected = module.select_pending_media_id(
        FakeClient(posts, media),
        "night_scout",
        permissions=permissions,
    )

    assert selected == "media-threads", selected

    assert module.external_unavailable_cooldown_active(
        media[0],
        now=now,
    )

    expired = {
        **media[0],
        "updated_at": (
            now
            - timedelta(
                seconds=module.EXTERNAL_UNAVAILABLE_RETRY_COOLDOWN_SECONDS + 60
            )
        ).isoformat(),
    }

    assert not module.external_unavailable_cooldown_active(
        expired,
        now=now,
    )

finally:
    module.core.safe_https_url = original_safe_url
    module.core.media_understanding_needs_refresh = original_understanding

    if original_env is None:
        os.environ.pop("ALLOW_LOCAL_TRANSCRIPTION", None)
    else:
        os.environ["ALLOW_LOCAL_TRANSCRIPTION"] = original_env

print("PASS test_direct_media_cross_platform_failsoft.py")
