#!/usr/bin/env python3
"""Threads remains a reference source, but new physical-media download is deferred."""
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
    try:
        ingest.download_source_media(
            media_url="https://scontent.example/video.mp4",
            canonical_post_url="https://www.threads.com/@approved/post/ABC123",
            path=Path("unused.mp4"),
            media_type="video",
            platform="threads",
        )
    except RuntimeError as exc:
        assert str(exc) == "physical_media_platform_deferred:threads", str(exc)
    else:
        raise AssertionError("Threads physical-media acquisition must be deferred")
    assert events == [], events
finally:
    ingest.download_direct_https_media = original_direct
    ingest.download_with_ytdlp = original_ytdlp

print("PASS test_threads_direct_video_download_fallback.py")
