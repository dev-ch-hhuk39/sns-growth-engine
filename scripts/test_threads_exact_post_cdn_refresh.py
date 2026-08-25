#!/usr/bin/env python3
"""Expired Threads media resolves from the exact parent and ordered child."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import ingest_direct_reference_media as ingest  # noqa: E402
from acquisition.router import BackendFailure  # noqa: E402
from acquisition.threads_public import ThreadsPublicHttpAdapter  # noqa: E402

parent = "https://www.threads.com/@approved/post/ABC123"
page = """
<meta property="og:description" content="same post text">
<meta property="og:video" content="https://cdninstagram.com/fresh.mp4">
"""
source = {
    "source_id": "src_threads",
    "source_url": "https://www.threads.com/@approved",
    "target_account_id": "night_scout",
}
adapter = ThreadsPublicHttpAdapter(html_loader=lambda url: page)
post = adapter.acquire_post(source, parent)
assert post.canonical_post_url == parent
assert post.media_items[0].source_post_id == post.source_post_id

try:
    adapter.acquire_post(source, "https://www.threads.com/@other/post/ABC123")
except BackendFailure as exc:
    assert str(exc) == "threads_post_author_mismatch"
else:
    raise AssertionError("another author must not be accepted")

old_safe = ingest.safe_https_url
try:
    ingest.safe_https_url = lambda *_args, **_kwargs: True
    refreshed, backend = ingest.refresh_threads_media_url(
        {
            "source_id": "src_threads",
            "profile_url": source["source_url"],
            "canonical_post_url": parent,
            "target_account_id": "night_scout",
        },
        {
            "source_post_id": post.source_post_id,
            "canonical_post_url": parent,
            "media_index": "0",
            "media_type": "video",
        },
        adapter=adapter,
    )
finally:
    ingest.safe_https_url = old_safe

assert refreshed == "https://cdninstagram.com/fresh.mp4"
assert backend == "threads_public_http"

original_download = ingest.download_direct_https_media
original_refresh = ingest.refresh_threads_media_url
events: list[str] = []
try:
    def download(url, *_args, **_kwargs):
        events.append(url)
        if len(events) == 1:
            raise OSError("expired")

    ingest.download_direct_https_media = download
    ingest.refresh_threads_media_url = lambda *_args, **_kwargs: (
        "https://cdninstagram.com/fresh.mp4",
        "threads_public_http",
    )
    resolution: dict[str, str] = {}
    provider = ingest.download_source_media(
        media_url="https://cdninstagram.com/expired.mp4",
        canonical_post_url=parent,
        path=Path("unused.mp4"),
        media_type="video",
        platform="threads",
        post={"source_id": "src_threads"},
        media={"media_index": "0"},
        resolution=resolution,
    )
finally:
    ingest.download_direct_https_media = original_download
    ingest.refresh_threads_media_url = original_refresh

assert events == [
    "https://cdninstagram.com/expired.mp4",
    "https://cdninstagram.com/fresh.mp4",
]
assert provider == "threads_public_http_refreshed_direct_http"
assert resolution["original_media_url"] == "https://cdninstagram.com/fresh.mp4"
print("PASS test_threads_exact_post_cdn_refresh.py")
