#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import acquire_approved_source_posts as acquisition


POST_ID = "sp_threads_legacy_1"
POST_URL = "https://www.threads.com/@approved/post/ABC123"
OLD_URL = "https://cdninstagram.com/expired.mp4"
NEW_URL = "https://cdninstagram.com/fresh.mp4"


def media_item(
    *,
    source_post_id=POST_ID,
    canonical_post_url=POST_URL,
    media_index=0,
    media_type="video",
    original_media_url=NEW_URL,
):
    return SimpleNamespace(
        source_post_id=source_post_id,
        canonical_post_url=canonical_post_url,
        media_index=media_index,
        media_type=media_type,
        original_media_url=original_media_url,
        resolver_backend="threads_public_http",
        thumbnail_url="",
    )


base = {
    "source_post_id": POST_ID,
    "canonical_post_url": POST_URL,
    "media_index": "0",
    "media_type": "video",
    "original_media_url": OLD_URL,
    "download_status": "FAILED",
    "cloudinary_status": "PENDING",
    "last_error": "ingest_failed:BackendFailure",
}

refresh = acquisition._volatile_threads_media_refresh(base, media_item())
assert refresh["original_media_url"] == NEW_URL
assert refresh["download_status"] == "PENDING"
assert refresh["cloudinary_status"] == "PENDING"
assert refresh["last_error"] == ""

same_url = acquisition._volatile_threads_media_refresh(
    base,
    media_item(original_media_url=OLD_URL),
)
assert same_url == {}

wrong_parent = acquisition._volatile_threads_media_refresh(
    base,
    media_item(source_post_id="sp_threads_other"),
)
assert wrong_parent == {}

integrity_failure = {
    **base,
    "last_error": "ingest_failed:threads_post_parent_mismatch",
}
assert acquisition._volatile_threads_media_refresh(
    integrity_failure,
    media_item(),
) == {}

legacy_index_error = {
    **base,
    "last_error": "ingest_failed:IndexError",
}
assert acquisition._volatile_threads_media_refresh(
    legacy_index_error,
    media_item(),
) == {}

print("PASS test_acquisition_recovers_legacy_threads_backend_failure.py")
