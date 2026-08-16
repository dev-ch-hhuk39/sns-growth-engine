"""Bounded TikTok profile discovery through the public embed payload.

TikTok's public embed page exposes a finite ``videoList`` in its Frontity
hydration data.  This adapter reads only that public payload: it does not use a
browser, cookies, login state, or an opaque scraping service.  Physical media
reuse remains a separate permission-gated operation.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.request import Request, urlopen

from .contracts import ProviderResult
from .models import (
    NormalizedMediaItem,
    NormalizedSourcePost,
    canonical_url,
    stable_content_hash,
    utc_now,
)
from .router import BackendFailure

MAX_PUBLIC_EMBED_BYTES = 3 * 1024 * 1024
MAX_TIKTOK_PROFILE_POSTS = 20
PROFILE = re.compile(r"^https://(?:www\.)?tiktok\.com/@(?P<handle>[A-Za-z0-9._-]+)$", re.I)
FRONTITY_SCRIPT = re.compile(
    r'<script[^>]+id=["\']__FRONTITY_CONNECT_STATE__["\'][^>]*>(?P<payload>.*?)</script>',
    re.I | re.S,
)


def _true(value: Any) -> bool:
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}


def _published_at(video_id: str) -> str:
    """Decode the public TikTok snowflake timestamp when it is plausible."""
    try:
        timestamp = int(video_id) >> 32
        value = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (OverflowError, OSError, TypeError, ValueError):
        return ""
    if not (2016 <= value.year <= datetime.now(timezone.utc).year + 1):
        return ""
    return value.isoformat()


def _profile_payload(document: dict[str, Any], handle: str) -> dict[str, Any]:
    data = document.get("source", {}).get("data", {})
    if not isinstance(data, dict):
        return {}
    expected = data.get(f"/embed/@{handle}")
    if isinstance(expected, dict) and isinstance(expected.get("videoList"), list):
        return expected
    for value in data.values():
        if isinstance(value, dict) and isinstance(value.get("videoList"), list):
            return value
    return {}


def parse_public_embed(page_html: str, *, expected_handle: str, limit: int) -> list[dict[str, Any]]:
    """Parse and validate a finite list of same-author public video records."""
    match = FRONTITY_SCRIPT.search(str(page_html or ""))
    if not match:
        raise BackendFailure("tiktok_public_embed_payload_unavailable")
    try:
        document = json.loads(html.unescape(match.group("payload")))
    except (json.JSONDecodeError, TypeError) as exc:
        raise BackendFailure("tiktok_public_embed_payload_invalid") from exc
    profile = _profile_payload(document, expected_handle)
    if not profile:
        raise BackendFailure("tiktok_public_embed_profile_unavailable")
    user = profile.get("userInfo") or {}
    observed = str(user.get("uniqueId") or "").lstrip("@").lower()
    if not observed or observed != expected_handle.lower():
        raise BackendFailure("tiktok_public_embed_author_mismatch")

    bounded = max(1, min(int(limit), MAX_TIKTOK_PROFILE_POSTS))
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in profile.get("videoList", []):
        if not isinstance(raw, dict) or raw.get("privateItem") is True:
            continue
        video_id = str(raw.get("id") or "")
        author = str(raw.get("authorUniqueId") or observed).lstrip("@").lower()
        play_url = str(raw.get("playAddr") or "")
        if not video_id.isdigit() or video_id in seen or author != observed:
            continue
        if not play_url.startswith("https://"):
            continue
        records.append(raw)
        seen.add(video_id)
        if len(records) >= bounded:
            break
    if not records:
        raise BackendFailure("tiktok_public_embed_individual_posts_unavailable")
    return records


class TikTokPublicEmbedAdapter:
    backend_name = "tiktok_public_embed"
    backend_version = "frontity-public-embed-v1"

    def __init__(self, html_loader: Callable[[str], str] | None = None):
        self._html_loader = html_loader

    def _load(self, url: str) -> str:
        if self._html_loader:
            return self._html_loader(url)
        request = Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/138.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "ja,en-US;q=0.8,en;q=0.7",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read(MAX_PUBLIC_EMBED_BYTES + 1)
        except Exception as exc:
            raise BackendFailure(f"tiktok_public_embed_http_failed:{type(exc).__name__}") from exc
        if len(payload) > MAX_PUBLIC_EMBED_BYTES:
            raise BackendFailure("tiktok_public_embed_response_too_large")
        return payload.decode("utf-8", errors="replace")

    def acquire(self, source: dict[str, Any], *, limit: int) -> list[NormalizedSourcePost]:
        platform = str(source.get("source_platform") or source.get("platform") or "").lower()
        if platform != "tiktok":
            raise BackendFailure("tiktok_public_embed_unsupported_platform")
        if not _true(source.get("fetch_enabled", True)):
            raise BackendFailure("tiktok_public_embed_source_not_fetch_enabled")
        profile_url = canonical_url(str(source.get("canonical_url") or source.get("source_url") or ""))
        profile_match = PROFILE.match(profile_url)
        if not profile_match:
            raise BackendFailure("tiktok_profile_url_required")
        handle = profile_match.group("handle")
        embed_url = f"https://www.tiktok.com/embed/@{handle}"
        try:
            start = max(1, int(source.get("_discovery_start_position", 1)))
        except (TypeError, ValueError):
            start = 1
        bounded = max(1, min(int(limit), MAX_TIKTOK_PROFILE_POSTS))
        requested = min(MAX_TIKTOK_PROFILE_POSTS, start - 1 + bounded)
        records = parse_public_embed(self._load(embed_url), expected_handle=handle, limit=requested)
        records = records[start - 1 : start - 1 + bounded]
        if not records:
            raise BackendFailure("tiktok_public_embed_page_exhausted")

        source_id = str(source.get("source_id") or "")
        targets = source.get("target_account_ids") or [source.get("target_account_id")]
        account_id = str(targets[0] if targets else "")
        posts: list[NormalizedSourcePost] = []
        for raw in records:
            video_id = str(raw["id"])
            post_url = canonical_url(f"https://www.tiktok.com/@{handle}/video/{video_id}")
            source_post_id = f"sp_{source_id}_{video_id}"
            play_url = str(raw["playAddr"])
            media_hash = hashlib.sha256(post_url.encode("utf-8")).hexdigest()
            media = NormalizedMediaItem(
                source_post_media_id=f"spm_{source_post_id}_0",
                source_post_id=source_post_id,
                media_index=0,
                media_type="video",
                canonical_post_url=post_url,
                original_media_url=play_url,
                resolver_backend=self.backend_name,
                mime_type="video/mp4",
                width=str(raw.get("width") or ""),
                height=str(raw.get("height") or ""),
                thumbnail_url=str(raw.get("originCoverUrl") or raw.get("coverUrl") or ""),
                content_hash=media_hash,
            )
            text = str(raw.get("desc") or "").strip()
            posts.append(
                NormalizedSourcePost(
                    source_post_id=source_post_id,
                    source_id=source_id,
                    target_account_id=account_id,
                    platform="tiktok",
                    profile_url=profile_url,
                    canonical_post_url=post_url,
                    external_post_id=video_id,
                    original_post_text=text,
                    published_at=_published_at(video_id),
                    author_handle=handle,
                    media_items=(media,),
                    engagement={"view_count": raw.get("playCount")},
                    collection_backend=self.backend_name,
                    backend_version=self.backend_version,
                    content_hash=stable_content_hash(text, [post_url]),
                    discovered_at=utc_now(),
                    detail_status="PASS",
                )
            )
        return posts

    def discover_profile(
        self, source: dict[str, Any], *, limit: int
    ) -> ProviderResult[list[NormalizedSourcePost]]:
        bounded = max(1, min(int(limit), MAX_TIKTOK_PROFILE_POSTS))
        try:
            posts = self.acquire(source, limit=bounded)
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                "PASS",
                data=posts,
                metadata={"limit": bounded, "public_embed_only": True},
            )
        except Exception as exc:
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                "FAILED",
                reason=str(exc) or f"{type(exc).__name__}:profile_discovery_failed",
                retryable=True,
                metadata={"limit": bounded, "public_embed_only": True},
            )
