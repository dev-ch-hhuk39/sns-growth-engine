#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import ingest_direct_reference_media_reliable as reliable


class FakeWorksheet:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]

    def get_all_records(self):
        return [dict(row) for row in self.rows]


class FakeClient:
    def __init__(self, posts, media):
        self.tabs = {
            "source_posts": FakeWorksheet(posts),
            "source_post_media": FakeWorksheet(media),
        }

    def _ws(self, logical):
        return self.tabs[logical]


def permission():
    return {
        "source_id": "source-threads",
        "updated_at": "2026-08-10T00:00:00+00:00",
        "permission_status": "approved",
        "rights_status": "approved_creator_clip",
        "allow_download": "true",
        "allow_cloudinary_storage": "true",
        "allow_original_repost": "true",
        "allow_new_caption": "true",
        "evidence_type": "contract",
        "evidence_reference": "fixture",
        "approved_by": "owner",
        "approved_at": "2026-08-10T00:00:00+00:00",
        "revoked": "false",
    }


cutoff = reliable.LEGACY_THREADS_INDEX_ERROR_RECOVERY_CUTOFF

post = {
    "source_post_id": "post-threads",
    "source_id": "source-threads",
    "target_account_id": "night_scout",
    "platform": "threads",
}

base_media = {
    "source_post_media_id": "media-threads",
    "source_post_id": "post-threads",
    "media_type": "video",
    "original_media_url": (
        "https://scontent.example.cdninstagram.com/"
        "o1/v/t16/f2/m84/legacy.mp4"
    ),
    "canonical_post_url": (
        "https://www.threads.com/@approved/post/ABC123"
    ),
    "download_status": "FAILED",
    "last_error": "ingest_failed:IndexError",
    "updated_at": (cutoff - timedelta(seconds=1)).isoformat(),
    "created_at": "2026-08-10T00:00:00+00:00",
}

assert reliable.legacy_threads_index_error_recoverable(
    base_media,
    "threads",
)

assert not reliable.legacy_threads_index_error_recoverable(
    {
        **base_media,
        "updated_at": cutoff.isoformat(),
    },
    "threads",
)

assert not reliable.legacy_threads_index_error_recoverable(
    {
        **base_media,
        "updated_at": (cutoff + timedelta(seconds=1)).isoformat(),
    },
    "threads",
)

assert not reliable.legacy_threads_index_error_recoverable(
    base_media,
    "youtube",
)

assert not reliable.legacy_threads_index_error_recoverable(
    {
        **base_media,
        "last_error": "ingest_failed:BackendFailure",
    },
    "threads",
)

assert not reliable.legacy_threads_index_error_recoverable(
    {
        **base_media,
        "last_error": "ingest_failed:threads_post_parent_mismatch",
    },
    "threads",
)

assert not reliable.legacy_threads_index_error_recoverable(
    {
        **base_media,
        "download_status": "BLOCKED",
    },
    "threads",
)

assert not reliable.legacy_threads_index_error_recoverable(
    {
        **base_media,
        "updated_at": "",
    },
    "threads",
)

original_safe_url = reliable.core.safe_https_url
original_local_transcription = os.environ.get(
    "ALLOW_LOCAL_TRANSCRIPTION"
)

try:
    reliable.core.safe_https_url = (
        lambda _url, stream_url=False: True
    )
    os.environ["ALLOW_LOCAL_TRANSCRIPTION"] = "false"

    client = FakeClient(
        [post],
        [base_media],
    )

    selected = reliable.select_pending_media_id(
        client,
        "night_scout",
        permissions=[permission()],
    )

    assert selected == "media-threads", selected

    current_failure = FakeClient(
        [post],
        [
            {
                **base_media,
                "updated_at": cutoff.isoformat(),
            }
        ],
    )

    selected = reliable.select_pending_media_id(
        current_failure,
        "night_scout",
        permissions=[permission()],
    )

    assert selected == "", selected

finally:
    reliable.core.safe_https_url = original_safe_url

    if original_local_transcription is None:
        os.environ.pop(
            "ALLOW_LOCAL_TRANSCRIPTION",
            None,
        )
    else:
        os.environ[
            "ALLOW_LOCAL_TRANSCRIPTION"
        ] = original_local_transcription

print(
    "PASS "
    "test_direct_media_recovers_legacy_threads_indexerror_once.py"
)
