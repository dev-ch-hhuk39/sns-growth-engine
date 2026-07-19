"""Bounded, cookie-free TikTok public-profile discovery fallback.

The primary TikTok backend remains yt-dlp.  This adapter only discovers
canonical individual video URLs from the public profile HTML when the primary
backend cannot enumerate a profile.  It never scrolls indefinitely, logs in,
persists browser state, or attempts to bypass platform controls.
"""
from __future__ import annotations

import html
import re
from typing import Any, Callable

from .contracts import ProviderResult
from .models import (
    NormalizedMediaItem,
    NormalizedSourcePost,
    canonical_url,
    external_post_id,
    stable_content_hash,
    utc_now,
)
from .router import BackendFailure

MAX_PUBLIC_PROFILE_POSTS = 20
TIKTOK_PROFILE = re.compile(r"^https://(?:www\.)?tiktok\.com/@(?P<handle>[A-Za-z0-9._-]+)$", re.I)


def extract_profile_video_urls(page_html: str, profile_url: str, *, limit: int) -> list[str]:
    """Return only videos belonging to the requested public profile handle."""
    normalized_profile = canonical_url(profile_url)
    match = TIKTOK_PROFILE.match(normalized_profile)
    if not match:
        return []
    handle = match.group("handle")
    # TikTok hydration data commonly escapes slashes and sometimes uses
    # unicode escapes.  Decode only those harmless representations before the
    # strict same-handle URL scan.
    decoded = html.unescape(str(page_html or ""))
    decoded = decoded.replace("\\u002F", "/").replace("\\/", "/")
    pattern = re.compile(
        rf"(?:https://(?:www\.)?tiktok\.com)?/@{re.escape(handle)}/video/(\d+)",
        re.I,
    )
    bounded = max(1, min(int(limit), MAX_PUBLIC_PROFILE_POSTS))
    urls: list[str] = []
    for video_id in pattern.findall(decoded):
        value = canonical_url(f"https://www.tiktok.com/@{handle}/video/{video_id}")
        if value not in urls:
            urls.append(value)
        if len(urls) >= bounded:
            break
    return urls


class TikTokPublicProfileAdapter:
    backend_name = "tiktok_public_playwright"
    backend_version = "public-html-v1"

    def __init__(self, html_loader: Callable[[str], str] | None = None):
        self._html_loader = html_loader

    def _load(self, url: str) -> str:
        if self._html_loader:
            return self._html_loader(url)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise BackendFailure("playwright_not_installed") from exc
        try:
            with sync_playwright() as browser_api:
                browser = browser_api.chromium.launch(headless=True)
                context = browser.new_context()  # Deliberately no cookies or storage state.
                page = context.new_page()
                page.set_default_timeout(30_000)
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(2_000)
                content = page.content()
                context.close()
                browser.close()
                return content
        except Exception as exc:
            raise BackendFailure(f"tiktok_public_page_failed:{type(exc).__name__}") from exc

    def acquire(self, source: dict[str, Any], *, limit: int) -> list[NormalizedSourcePost]:
        platform = str(source.get("source_platform") or source.get("platform") or "").lower()
        if platform != "tiktok":
            raise BackendFailure(f"tiktok_public_unsupported_platform:{platform}")
        profile_url = canonical_url(str(source.get("canonical_url") or source.get("source_url") or ""))
        if not TIKTOK_PROFILE.match(profile_url):
            raise BackendFailure("tiktok_profile_url_required")
        bounded = max(1, min(int(limit), MAX_PUBLIC_PROFILE_POSTS))
        urls = extract_profile_video_urls(self._load(profile_url), profile_url, limit=bounded)
        if not urls:
            raise BackendFailure("tiktok_profile_video_links_unavailable")

        source_id = str(source.get("source_id") or "")
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        account_id = str(targets[0] if targets else "")
        handle = TIKTOK_PROFILE.match(profile_url).group("handle")  # validated above
        posts: list[NormalizedSourcePost] = []
        for post_url in urls:
            post_external_id = external_post_id(post_url)
            post_id = f"sp_{source_id}_{post_external_id}"
            media = NormalizedMediaItem(
                source_post_media_id=f"spm_{post_id}_0",
                source_post_id=post_id,
                media_index=0,
                media_type="video",
                canonical_post_url=post_url,
                original_media_url=post_url,
                resolver_backend=self.backend_name,
            )
            posts.append(NormalizedSourcePost(
                source_post_id=post_id,
                source_id=source_id,
                target_account_id=account_id,
                platform="tiktok",
                profile_url=profile_url,
                canonical_post_url=post_url,
                external_post_id=post_external_id,
                original_post_text="",
                published_at="",
                author_handle=handle,
                media_items=(media,),
                collection_backend=self.backend_name,
                backend_version=self.backend_version,
                content_hash=stable_content_hash("", [post_url]),
                discovered_at=utc_now(),
            ))
        return posts

    def discover_profile(self, source: dict[str, Any], *, limit: int) -> ProviderResult[list[NormalizedSourcePost]]:
        bounded = max(1, min(int(limit), MAX_PUBLIC_PROFILE_POSTS))
        try:
            posts = self.acquire(source, limit=bounded)
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                "PASS",
                data=posts,
                metadata={"limit": bounded, "public_profile_only": True},
            )
        except Exception as exc:
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                "FAILED",
                reason=f"{type(exc).__name__}:tiktok_profile_discovery_failed",
                retryable=True,
                metadata={"limit": bounded, "public_profile_only": True},
            )
