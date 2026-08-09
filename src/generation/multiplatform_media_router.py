"""Platform-aware routing policy for user-authorized reference media.

This module is policy-only. It does not publish, mutate Sheets, upload media,
or log credentials. Concrete provider execution stays bounded in the caller.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Iterable
from urllib.parse import urlparse

SUPPORTED_PLATFORMS = {"youtube", "tiktok", "threads", "x"}
PLATFORM_PRIORITY = {"threads": 0, "tiktok": 1, "x": 2, "youtube": 3}
PROVIDER_CHAINS = {
    "youtube": ("yt_dlp",),
    "tiktok": ("direct_http", "gallery_dl", "yt_dlp"),
    "threads": ("direct_http", "threads_public_router"),
    "x": ("direct_http", "gallery_dl"),
}


def text(value: Any) -> str:
    return str(value or "").strip()


def target_accounts(source: dict[str, Any]) -> list[str]:
    raw = source.get("target_account_ids")
    if isinstance(raw, list):
        return [text(value) for value in raw if text(value)]
    value = text(source.get("target_account_id") or source.get("account_id"))
    return [value] if value else []


def normalize_platform(value: Any = "", url: str = "") -> str:
    raw = text(value).lower().replace("twitter", "x")
    aliases = {"youtube_shorts": "youtube", "youtube_playlist": "youtube", "youtube_streams": "youtube"}
    raw = aliases.get(raw, raw)
    if raw in SUPPORTED_PLATFORMS:
        return raw
    host = (urlparse(text(url)).hostname or "").lower()
    if "youtu.be" in host or "youtube.com" in host:
        return "youtube"
    if "tiktok.com" in host:
        return "tiktok"
    if "threads.com" in host or "threads.net" in host:
        return "threads"
    if host == "x.com" or host.endswith(".x.com") or "twitter.com" in host:
        return "x"
    return ""


def provider_chain(platform: str) -> tuple[str, ...]:
    return PROVIDER_CHAINS.get(normalize_platform(platform), ("direct_http",))


def source_rank(source: dict[str, Any]) -> tuple[int, int, str]:
    platform = normalize_platform(
        source.get("source_platform") or source.get("platform"),
        text(source.get("source_url") or source.get("canonical_url")),
    )
    active = text(source.get("active")).lower() in {"1", "true", "yes", "active"}
    return (0 if active else 1, PLATFORM_PRIORITY.get(platform, 9), text(source.get("source_id")))


def merge_designated_sources(
    account_id: str,
    *source_sets: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge Sheet + user-provided config sources for local review only.

    The current user confirmation is the authorization basis. This function
    never persists or silently changes source registry policy.
    """
    merged: dict[str, dict[str, Any]] = {}
    for rows in source_sets:
        for original in rows:
            row = dict(original)
            if account_id not in target_accounts(row):
                continue
            url = text(row.get("source_url") or row.get("canonical_url") or row.get("post_url"))
            platform = normalize_platform(row.get("source_platform") or row.get("platform"), url)
            if platform not in SUPPORTED_PLATFORMS or not url:
                continue
            source_id = text(row.get("source_id"))
            key = source_id or f"{platform}:{url.rstrip('/').lower()}"
            row["_resolved_platform"] = platform
            row["_authorization_basis"] = "user_confirmed_designated_reference_source_20260809"
            if key in merged:
                prior = merged[key]
                # Live Sheet data wins field-by-field; config fills blanks.
                combined = dict(row)
                combined.update({k: v for k, v in prior.items() if text(v)})
                merged[key] = combined
            else:
                merged[key] = row
    return sorted(merged.values(), key=source_rank)


def platform_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rows:
        platform = normalize_platform(
            row.get("_resolved_platform") or row.get("source_platform") or row.get("platform"),
            text(row.get("source_url") or row.get("canonical_url") or row.get("post_url")),
        )
        if platform:
            counter[platform] += 1
    return dict(sorted(counter.items()))
