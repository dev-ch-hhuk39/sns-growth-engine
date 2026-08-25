#!/usr/bin/env python3
"""YouTube physical downloads get one bounded public-client fallback."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.ytdlp_runtime import (  # noqa: E402
    YOUTUBE_BOUNDED_AV_FORMAT,
    YOUTUBE_PUBLIC_PLAYER_FALLBACK,
    physical_download_option_attempts,
)


base = {
    "format": "bestvideo+bestaudio/best",
    "noplaylist": True,
    "extractor_args": {"youtube": {"lang": ["ja"]}},
}
youtube = physical_download_option_attempts("youtube", base)
assert len(youtube) == 2, youtube
assert youtube[0]["format"] == base["format"]
assert youtube[1]["format"] == YOUTUBE_BOUNDED_AV_FORMAT
assert youtube[1]["extractor_args"]["youtube"]["player_client"] == [
    YOUTUBE_PUBLIC_PLAYER_FALLBACK
]
assert youtube[1]["extractor_args"]["youtube"]["lang"] == ["ja"]
assert "player_client" not in base["extractor_args"]["youtube"]
assert len(physical_download_option_attempts("tiktok", base)) == 1

for relative in (
    "scripts/ingest_direct_reference_media.py",
    "scripts/download_approved_media.py",
    "src/video/video_downloader.py",
):
    text = (ROOT / relative).read_text(encoding="utf-8")
    assert "physical_download_option_attempts" in text, relative

print("PASS test_ytdlp_physical_download_fallback.py")
