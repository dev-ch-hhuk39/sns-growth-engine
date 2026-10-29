"""Single source of truth for reference discovery vs physical media acquisition."""
from __future__ import annotations

from urllib.parse import urlparse
from typing import Any

REFERENCE_PLATFORMS = ("tiktok", "threads", "x", "youtube")
DEFERRED_REFERENCE_PLATFORMS: tuple[str, ...] = ()
KNOWN_REFERENCE_PLATFORMS = REFERENCE_PLATFORMS + DEFERRED_REFERENCE_PLATFORMS
REFERENCE_PLATFORM_PRIORITY = {platform: rank for rank, platform in enumerate(REFERENCE_PLATFORMS)}
OWNER_REFERENCE_ACCOUNTS = ("night_scout", "liver_manager")
PHYSICAL_MEDIA_PLATFORMS_BY_ACCOUNT = {account: ("x", "youtube") for account in OWNER_REFERENCE_ACCOUNTS}
DEFERRED_PHYSICAL_MEDIA_PLATFORMS_BY_ACCOUNT = {account: ("tiktok", "threads") for account in OWNER_REFERENCE_ACCOUNTS}
DEFERRED_REFERENCE_STATUS = "DEFERRED_OSS_CANDIDATE"
DEFERRED_REFERENCE_REASON = (
    "NO_APPROVED_BACKEND_ONLY_GITHUB_OSS_ROUTE_CURRENTLY_PROVEN"
)
PHYSICAL_MEDIA_PLATFORMS = ("threads", "x", "youtube", "tiktok")
DEFERRED_PHYSICAL_MEDIA_PLATFORMS: tuple[str, ...] = ()
PHYSICAL_MEDIA_PROVIDER = {
    "threads": "public_og_direct_http",
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
    if raw in KNOWN_REFERENCE_PLATFORMS:
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


def can_attempt_physical_media(platform: Any = "", url: str = "", *, account_id: str = "") -> bool:
    # Retain the legacy capability API; active account entrypoints must supply
    # their verified account so permission alone cannot activate deferred media.
    allowed = PHYSICAL_MEDIA_PLATFORMS_BY_ACCOUNT.get(account_id, PHYSICAL_MEDIA_PLATFORMS)
    normalized = normalize_platform(platform, url)
    inferred = normalize_platform("", url)
    if account_id in OWNER_REFERENCE_ACCOUNTS and inferred and inferred != normalized:
        return False
    return normalized in allowed


def physical_media_provider(platform: Any = "", url: str = "", *, account_id: str = "") -> str:
    if not can_attempt_physical_media(platform, url, account_id=account_id):
        return ""
    return PHYSICAL_MEDIA_PROVIDER.get(normalize_platform(platform, url), "")


def order_reference_sources(sources: list[dict[str, Any]], *, account_id: str) -> list[dict[str, Any]]:
    """Apply owner discovery order before bounds, retaining other account slots."""
    def priority(source: dict[str, Any]) -> int:
        platform = normalize_platform(
            source.get("source_platform") or source.get("platform"),
            _text(source.get("source_url") or source.get("url") or source.get("canonical_url")),
        )
        return REFERENCE_PLATFORM_PRIORITY.get(platform, len(REFERENCE_PLATFORMS))

    if account_id in OWNER_REFERENCE_ACCOUNTS:
        return sorted(sources, key=priority)
    ordered = list(sources)
    if account_id == "all":
        for owner in OWNER_REFERENCE_ACCOUNTS:
            positions = []
            for index, source in enumerate(sources):
                targets = source.get("target_account_ids")
                target = targets[0] if isinstance(targets, list) and targets else (
                    source.get("target_account_id") or source.get("account_id")
                )
                if target == owner:
                    positions.append(index)
            for index, source in zip(positions, sorted((sources[i] for i in positions), key=priority)):
                ordered[index] = source
    return ordered


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
