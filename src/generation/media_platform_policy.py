"""Single source of truth for reference discovery vs physical media acquisition."""
from __future__ import annotations

from urllib.parse import urlparse
from typing import Any

REFERENCE_PLATFORMS = ("tiktok", "threads", "x", "youtube")
REFERENCE_PLATFORM_PRIORITY = {"tiktok": 0, "threads": 1, "x": 2, "youtube": 3}
PHYSICAL_MEDIA_PLATFORMS = ("x", "youtube")
DEFERRED_PHYSICAL_MEDIA_PLATFORMS = ("tiktok", "threads")
PHYSICAL_MEDIA_PROVIDER = {"x": "yt_dlp", "youtube": "yt_dlp"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def normalize_platform(value: Any = "", url: str = "") -> str:
    raw = _text(value).lower().replace("twitter", "x")
    aliases = {
        "youtube_shorts": "youtube",
        "youtube_playlist": "youtube",
        "youtube_streams": "youtube",
    }
    raw = aliases.get(raw, raw)
    if raw in REFERENCE_PLATFORMS:
        return raw
    host = (urlparse(_text(url)).hostname or "").lower()
    if "youtu.be" in host or "youtube.com" in host:
        return "youtube"
    if "tiktok.com" in host:
        return "tiktok"
    if "threads.com" in host or "threads.net" in host:
        return "threads"
    if host == "x.com" or host.endswith(".x.com") or "twitter.com" in host:
        return "x"
    return ""


def can_attempt_physical_media(platform: Any = "", url: str = "") -> bool:
    return normalize_platform(platform, url) in PHYSICAL_MEDIA_PLATFORMS


def physical_media_provider(platform: Any = "", url: str = "") -> str:
    return PHYSICAL_MEDIA_PROVIDER.get(normalize_platform(platform, url), "")


def reference_priority_score(platform: Any = "", url: str = "") -> float:
    """Return a stable 0..1 score that preserves the canonical order."""
    normalized = normalize_platform(platform, url)
    rank = REFERENCE_PLATFORM_PRIORITY.get(normalized)
    if rank is None:
        return 0.0
    return 1.0 - (rank * 0.2)
