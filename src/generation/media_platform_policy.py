"""Single source of truth for reference discovery vs physical media acquisition."""
from __future__ import annotations

from urllib.parse import urlparse
from typing import Any

REFERENCE_PLATFORMS = ("tiktok", "threads", "x", "youtube")
REFERENCE_PLATFORM_PRIORITY = {"tiktok": 0, "threads": 1, "x": 2, "youtube": 3}
PHYSICAL_MEDIA_PLATFORMS = ("x", "youtube", "tiktok")
DEFERRED_PHYSICAL_MEDIA_PLATFORMS = ("threads",)
PHYSICAL_MEDIA_PROVIDER = {
    "x": "yt_dlp",
    "youtube": "yt_dlp",
    "tiktok": "public_embed_direct_http",
}


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


def is_retired_source(source: dict[str, Any]) -> bool:
    """Return true for owner-retired sources regardless of stale active flags."""
    return bool(source.get("retired_from_runtime_selection")) or _text(
        source.get("editorial_selection_status")
    ).lower() == "retired"


def select_x_video_primary_sources(
    sources: list[dict[str, Any]], account_id: str = "night_scout"
) -> list[dict[str, Any]]:
    """Select editorially approved X video sources without inferring rights.

    Editorial fitness and effective permission are independent gates. Physical
    acquisition must still pass the permission ledger after this selection.
    """
    selected: list[dict[str, Any]] = []
    for source in sources:
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        if account_id not in {_text(value) for value in targets if _text(value)}:
            continue
        if normalize_platform(
            source.get("source_platform") or source.get("platform"),
            _text(source.get("canonical_url") or source.get("source_url")),
        ) != "x":
            continue
        if is_retired_source(source) or source.get("x_video_candidate_enabled") is not True:
            continue
        selected.append(source)
    return sorted(
        selected,
        key=lambda row: (
            int(row.get("x_video_candidate_priority") or 999),
            _text(row.get("source_id")),
        ),
    )
