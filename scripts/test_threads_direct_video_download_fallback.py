#!/usr/bin/env python3
"""Threads direct media uses the bounded CDN path, never a profile extractor."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]
import ingest_direct_reference_media as ingest  # noqa: E402

events = []
original_direct = ingest.download_direct_https_media
original_ytdlp = ingest.download_with_ytdlp
try:
    ingest.download_direct_https_media = lambda *_a, **_k: events.append("direct")
    ingest.download_with_ytdlp = lambda *_a, **_k: events.append("yt_dlp")
    provider = ingest.download_source_media(
        media_url="https://scontent.example/video.mp4",
        canonical_post_url="https://www.threads.com/@approved/post/ABC123",
        path=Path("unused.mp4"),
        media_type="video",
        platform="threads",
    )
    assert provider == "threads_public_og_direct_http", provider
    assert events == ["direct"], events

    try:
        ingest.download_source_media(
            media_url="https://scontent.example/video.mp4",
            canonical_post_url="https://www.threads.com/@approved",
            path=Path("unused.mp4"),
            media_type="video",
            platform="threads",
        )
    except RuntimeError as exc:
        assert str(exc) == "threads_individual_post_url_required", str(exc)
    else:
        raise AssertionError("Threads profile URLs must never be downloaded")
finally:
    ingest.download_direct_https_media = original_direct
    ingest.download_with_ytdlp = original_ytdlp

print("PASS test_threads_direct_video_download_fallback.py")
