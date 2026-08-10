#!/usr/bin/env python3
"""Threads video fallback stays bounded to its exact individual post."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

import ingest_direct_reference_media as ingest  # noqa: E402


events: list[tuple[str, str]] = []
original_direct = ingest.download_direct_https_media
original_ytdlp = ingest.download_with_ytdlp
original_safe_url = ingest.safe_https_url
try:
    def fail_direct(url: str, _path: Path, *, media_type: str) -> None:
        events.append(("direct", f"{media_type}:{url}"))
        raise RuntimeError("expired_fixture")

    def ytdlp(url: str, _path: Path) -> None:
        events.append(("yt_dlp", url))

    ingest.download_direct_https_media = fail_direct
    ingest.download_with_ytdlp = ytdlp
    ingest.safe_https_url = lambda url, **_kwargs: url.startswith("https://www.threads.com/")
    backend = ingest.download_source_media(
        media_url="https://scontent.example/video.mp4",
        canonical_post_url="https://www.threads.com/@approved/post/ABC123",
        path=Path("unused.mp4"),
        media_type="video",
        platform="threads",
    )
    assert backend == "threads_individual_post_ytdlp_fallback"
    assert events[-1] == ("yt_dlp", "https://www.threads.com/@approved/post/ABC123")

    for media_type, post_url in (
        ("image", "https://www.threads.com/@approved/post/ABC123"),
        ("video", "https://www.threads.com/@approved"),
    ):
        try:
            ingest.download_source_media(
                media_url="https://scontent.example/media.bin",
                canonical_post_url=post_url,
                path=Path("unused.bin"),
                media_type=media_type,
                platform="threads",
            )
        except RuntimeError as exc:
            assert str(exc) == "expired_fixture"
        else:
            raise AssertionError("non-video or profile URL must not use fallback")
finally:
    ingest.download_direct_https_media = original_direct
    ingest.download_with_ytdlp = original_ytdlp
    ingest.safe_https_url = original_safe_url

print("PASS test_threads_direct_video_download_fallback.py")
