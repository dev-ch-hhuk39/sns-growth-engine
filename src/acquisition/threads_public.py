"""Cookie-free, serial public Threads profile and post adapters.

This deliberately avoids private GraphQL calls, token capture, stealth plugins,
stored browser state and CAPTCHA workarounds.  It reads only public HTML from
one browser context at a time and reports an ordinary backend failure when a
profile no longer exposes post links.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urljoin

from .models import NormalizedMediaItem, NormalizedSourcePost, canonical_url, external_post_id, stable_content_hash, utc_now
from .router import BackendFailure

POST_HREF = re.compile(r"/(?:@[^/]+/)?post/[A-Za-z0-9_-]+")
META = re.compile(r"<meta[^>]+(?:property|name)=[\"'](?P<key>[^\"']+)[\"'][^>]+content=[\"'](?P<value>[^\"']+)[\"'][^>]*>", re.I)


def _meta_values(page_html: str, key: str) -> list[str]:
    values = []
    for match in META.finditer(page_html):
        if match.group("key").lower() == key.lower():
            values.append(html.unescape(match.group("value")))
    return list(dict.fromkeys(values))


def extract_profile_post_urls(page_html: str, profile_url: str, *, limit: int) -> list[str]:
    """Extract stable public post paths from a public profile page."""
    paths = []
    for match in POST_HREF.finditer(page_html):
        path = match.group(0)
        value = canonical_url(urljoin(profile_url, path))
        if value not in paths:
            paths.append(value)
        if len(paths) >= limit:
            break
    return paths


def parse_public_post_html(
    source: dict[str, Any],
    post_url: str,
    page_html: str,
    *,
    backend_name: str = "threads_public_playwright",
    backend_version: str = "public-html-v1",
) -> NormalizedSourcePost:
    """Normalize one public post page without retaining the raw HTML."""
    canonical_post = canonical_url(post_url)
    external = external_post_id(canonical_post)
    source_id = str(source["source_id"])
    post_id = f"sp_{source_id}_{external}"
    description = _meta_values(page_html, "og:description") or _meta_values(page_html, "description")
    original_text = description[0] if description else ""
    author = _meta_values(page_html, "og:title")
    image_urls = _meta_values(page_html, "og:image")
    video_urls = _meta_values(page_html, "og:video") + _meta_values(page_html, "og:video:secure_url")
    media: list[NormalizedMediaItem] = []
    ordered: list[tuple[str, str]] = [("image", url) for url in image_urls] + [("video", url) for url in video_urls]
    for index, (media_type, media_url) in enumerate(dict.fromkeys(ordered)):
        media.append(NormalizedMediaItem(
            source_post_media_id=f"spm_{post_id}_{index}",
            source_post_id=post_id,
            media_index=index,
            media_type=media_type,
            canonical_post_url=canonical_post,
            original_media_url=canonical_url(media_url),
            resolver_backend=backend_name,
            thumbnail_url=image_urls[0] if media_type == "video" and image_urls else "",
        ))
    account_id = str((source.get("target_account_ids") or [source.get("target_account_id")])[0] or "")
    handle = ""
    match = re.search(r"/@([^/]+)/post/", canonical_post)
    if match:
        handle = match.group(1)
    return NormalizedSourcePost(
        source_post_id=post_id,
        source_id=source_id,
        target_account_id=account_id,
        platform="threads",
        profile_url=canonical_url(str(source.get("source_url") or "")),
        canonical_post_url=canonical_post,
        external_post_id=external,
        original_post_text=original_text,
        published_at="",
        author_name=author[0] if author else "",
        author_handle=handle,
        media_items=tuple(media),
        engagement={},
        collection_backend=backend_name,
        backend_version=backend_version,
        content_hash=stable_content_hash(original_text, [item.original_media_url for item in media]),
        discovered_at=utc_now(),
    )


class ThreadsPublicProfileAdapter:
    backend_name = "threads_public_playwright"
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
                context = browser.new_context()  # No cookies, storage state or shared profile.
                page = context.new_page()
                page.set_default_timeout(30_000)
                page.goto(url, wait_until="domcontentloaded")
                content = page.content()
                context.close()
                browser.close()
                return content
        except Exception as exc:
            raise BackendFailure(f"threads_public_page_failed:{type(exc).__name__}") from exc

    def acquire(self, source: dict[str, Any], *, limit: int) -> list[NormalizedSourcePost]:
        profile_url = canonical_url(str(source.get("source_url") or ""))
        if not profile_url.startswith("https://www.threads.com/@"):
            raise BackendFailure("threads_profile_url_required")
        profile_html = self._load(profile_url)
        post_urls = extract_profile_post_urls(profile_html, profile_url, limit=limit)
        if not post_urls:
            raise BackendFailure("threads_profile_post_links_unavailable")
        posts = []
        for post_url in post_urls:
            try:
                posts.append(parse_public_post_html(source, post_url, self._load(post_url), backend_name=self.backend_name, backend_version=self.backend_version))
            except BackendFailure:
                continue
        if not posts:
            raise BackendFailure("threads_post_detail_unavailable")
        return posts


class ThreadsPublicHttpAdapter(ThreadsPublicProfileAdapter):
    """Lightweight fallback for public pages when Chromium is unavailable."""

    backend_name = "threads_public_http"
    backend_version = "public-http-v1"

    def _load(self, url: str) -> str:
        if self._html_loader:
            return self._html_loader(url)
        try:
            from urllib.request import Request, urlopen
            request = Request(url, headers={"User-Agent": "SNSGrowthEngine/1.0 public-source-collector"})
            with urlopen(request, timeout=20) as response:
                if response.status != 200:
                    raise BackendFailure(f"threads_http_status:{response.status}")
                return response.read(2_000_000).decode("utf-8", errors="replace")
        except BackendFailure:
            raise
        except Exception as exc:
            raise BackendFailure(f"threads_public_http_failed:{type(exc).__name__}") from exc
