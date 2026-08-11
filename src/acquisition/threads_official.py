"""Official backend-only Threads discovery and individual-post detail.

The Graph adapter is optional-auth and uses only documented public profile
discovery fields.  The oEmbed adapter is tokenless, but accepts only canonical
individual post URLs.  Neither adapter uses browser state or private APIs.
"""
from __future__ import annotations

import html
import json
import os
import re
from html.parser import HTMLParser
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .contracts import ProviderResult
from .models import (
    NormalizedMediaItem,
    NormalizedSourcePost,
    canonical_url,
    external_post_id,
    stable_content_hash,
    utc_now,
)

GRAPH_ROOT = "https://graph.threads.net"
OEMBED_ENDPOINT = "https://graph.threads.com/oembed"
GRAPH_FIELDS = (
    "id,media_product_type,media_type,media_url,permalink,owner,username,"
    "text,timestamp,shortcode,thumbnail_url,children,is_quote_post,quoted_post,"
    "reposted_post,has_replies,alt_text,link_attachment_url"
)
_POST_URL = re.compile(
    r"^https://(?:www\.)?threads\.(?:com|net)/(?:@(?P<handle>[^/]+)/post/|t/)(?P<code>[A-Za-z0-9_-]+)$",
    re.I,
)


def threads_handle(value: str) -> str:
    match = re.search(r"/@([^/?#]+)", canonical_url(value))
    return match.group(1).lower() if match else ""


def canonical_threads_post_url(value: str) -> str:
    normalized = canonical_url(value)
    match = _POST_URL.fullmatch(normalized)
    if not match:
        return ""
    handle = match.group("handle")
    if handle:
        return f"https://www.threads.com/@{handle.lower()}/post/{match.group('code')}"
    return f"https://www.threads.com/t/{match.group('code')}"


def _target_account(source: dict[str, Any]) -> str:
    return str((source.get("target_account_ids") or [source.get("target_account_id")])[0] or "")


def _json_get(url: str, headers: dict[str, str]) -> dict[str, Any]:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise RuntimeError(f"http_status:{response.status}")
        payload = json.loads(response.read(2_000_000).decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("invalid_json_payload")
    return payload


def _is_quote_or_repost(row: dict[str, Any]) -> bool:
    return bool(
        row.get("is_quote_post")
        or row.get("quoted_post")
        or row.get("reposted_post")
        or str(row.get("media_product_type") or "").upper() == "REPOST"
    )


def normalize_graph_post(source: dict[str, Any], row: dict[str, Any]) -> NormalizedSourcePost:
    expected = threads_handle(str(source.get("source_url") or ""))
    author = str(row.get("username") or "").lower().lstrip("@")
    permalink = canonical_threads_post_url(str(row.get("permalink") or ""))
    if not permalink:
        raise ValueError("threads_individual_post_url_required")
    permalink_author = threads_handle(permalink)
    if expected and author != expected:
        raise ValueError("threads_author_mismatch")
    if permalink_author and expected and permalink_author != expected:
        raise ValueError("threads_permalink_author_mismatch")

    source_id = str(source.get("source_id") or "")
    external = str(row.get("id") or external_post_id(permalink))
    source_post_id = f"sp_{source_id}_{external}"
    media_rows: list[dict[str, Any]] = []
    media_type = str(row.get("media_type") or "").upper()
    children = row.get("children")
    if isinstance(children, dict):
        children = children.get("data")
    if media_type == "CAROUSEL_ALBUM" and isinstance(children, list):
        media_rows = [child for child in children if isinstance(child, dict)]
    elif media_type in {"IMAGE", "VIDEO"}:
        media_rows = [row]

    media: list[NormalizedMediaItem] = []
    # A quote/repost permission belongs to the registered source's own post,
    # never to the quoted author's media. Preserve text/provenance only.
    if not _is_quote_or_repost(row):
        for child in media_rows:
            kind = str(child.get("media_type") or "").lower()
            media_url = canonical_url(str(child.get("media_url") or ""))
            if kind not in {"image", "video"} or not media_url.startswith("https://"):
                continue
            index = len(media)
            media.append(
                NormalizedMediaItem(
                    source_post_media_id=f"spm_{source_post_id}_{index}",
                    source_post_id=source_post_id,
                    media_index=index,
                    media_type=kind,
                    canonical_post_url=permalink,
                    original_media_url=media_url,
                    resolver_backend="threads_graph_public_discovery",
                    thumbnail_url=canonical_url(str(child.get("thumbnail_url") or "")),
                )
            )

    text = str(row.get("text") or "").strip()
    return NormalizedSourcePost(
        source_post_id=source_post_id,
        source_id=source_id,
        target_account_id=_target_account(source),
        platform="threads",
        profile_url=canonical_url(str(source.get("source_url") or "")),
        canonical_post_url=permalink,
        external_post_id=external,
        original_post_text=text,
        published_at=str(row.get("timestamp") or ""),
        author_handle=author,
        media_items=tuple(media),
        engagement={},
        collection_backend="threads_graph_public_discovery",
        backend_version="graph-public-v1",
        content_hash=stable_content_hash(text, [item.original_media_url for item in media]),
        discovered_at=utc_now(),
        detail_status="PARTIAL" if _is_quote_or_repost(row) else "PASS",
    )


class ThreadsGraphPublicDiscoveryAdapter:
    backend_name = "threads_graph_public_discovery"
    backend_version = "graph-public-v1"

    def __init__(
        self,
        json_loader: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
        token_loader: Callable[[], str] | None = None,
    ):
        self._json_loader = json_loader or _json_get
        self._token_loader = token_loader or (lambda: os.environ.get("THREADS_DISCOVERY_ACCESS_TOKEN", ""))

    @classmethod
    def capability_status(cls) -> ProviderResult[dict[str, Any]]:
        auth_present = bool(os.environ.get("THREADS_DISCOVERY_ACCESS_TOKEN"))
        return ProviderResult(
            cls.backend_name,
            cls.backend_version,
            "PASS" if auth_present else "BLOCKED",
            data={"auth_present": auth_present, "active": auth_present, "browser_required": False},
            reason="" if auth_present else "AUTH_REQUIRED:threads_profile_discovery",
        )

    def discover_profile(
        self, source: dict[str, Any], *, limit: int
    ) -> ProviderResult[list[NormalizedSourcePost]]:
        token = self._token_loader().strip()
        if not token:
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                "BLOCKED",
                data=[],
                reason="AUTH_REQUIRED:threads_profile_discovery",
            )
        handle = threads_handle(str(source.get("source_url") or ""))
        if not handle:
            return ProviderResult(self.backend_name, self.backend_version, "BLOCKED", data=[], reason="threads_profile_handle_required")
        bounded = min(25, max(1, int(limit)))
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            profile_url = f"{GRAPH_ROOT}/profile_lookup?{urlencode({'username': handle})}"
            profile = self._json_loader(profile_url, headers)
            profile_data = profile.get("data")
            profile_user = str(
                profile.get("username")
                or (profile_data.get("username") if isinstance(profile_data, dict) else "")
                or ""
            ).lower().lstrip("@")
            if profile_user and profile_user != handle:
                raise ValueError("threads_profile_identity_mismatch")
            posts_url = f"{GRAPH_ROOT}/profile_posts?{urlencode({'username': handle, 'fields': GRAPH_FIELDS, 'limit': bounded})}"
            payload = self._json_loader(posts_url, headers)
            rows = payload.get("data") or []
            if not isinstance(rows, list):
                raise ValueError("threads_profile_posts_payload_invalid")
            posts: list[NormalizedSourcePost] = []
            for row in rows[:bounded]:
                if not isinstance(row, dict):
                    continue
                posts.append(normalize_graph_post(source, row))
            status = "PASS" if posts else "PARTIAL"
            return ProviderResult(self.backend_name, self.backend_version, status, data=posts, reason="" if posts else "NO_PUBLIC_POSTS")
        except Exception as exc:
            reason = str(exc) or type(exc).__name__
            if "401" in reason or "403" in reason:
                reason = "AUTH_REQUIRED_OR_ADVANCED_ACCESS"
            return ProviderResult(self.backend_name, self.backend_version, "FAILED", data=[], reason=reason, retryable=False)

    def search_posts(
        self,
        source: dict[str, Any],
        query: str,
        *,
        limit: int,
        search_type: str = "RECENT",
    ) -> ProviderResult[list[NormalizedSourcePost]]:
        """Run documented keyword search, retaining only the registered author."""
        token = self._token_loader().strip()
        if not token:
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                "BLOCKED",
                data=[],
                reason="AUTH_REQUIRED:threads_keyword_search",
            )
        bounded = min(25, max(1, int(limit)))
        mode = search_type.upper()
        if mode not in {"TOP", "RECENT"} or not str(query).strip():
            return ProviderResult(self.backend_name, self.backend_version, "BLOCKED", data=[], reason="invalid_keyword_search_request")
        endpoint = f"{GRAPH_ROOT}/keyword_search?{urlencode({'q': str(query).strip(), 'search_type': mode, 'fields': GRAPH_FIELDS, 'limit': bounded})}"
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        try:
            payload = self._json_loader(endpoint, headers)
            rows = payload.get("data") or []
            posts: list[NormalizedSourcePost] = []
            rejected = 0
            for row in rows[:bounded] if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                try:
                    posts.append(normalize_graph_post(source, row))
                except ValueError:
                    rejected += 1
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                "PASS" if posts else "PARTIAL",
                data=posts,
                reason="" if posts else "NO_REGISTERED_AUTHOR_RESULTS",
                metadata={"rejected_author_count": rejected, "bounded_limit": bounded, "search_type": mode},
            )
        except Exception as exc:
            return ProviderResult(self.backend_name, self.backend_version, "FAILED", data=[], reason=str(exc) or type(exc).__name__)


class _EmbedParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.video_urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        # Only an explicit video/source element proves a physical video URL.
        if tag.lower() in {"video", "source"}:
            src = str(values.get("src") or "")
            if src.startswith("https://") and src not in self.video_urls:
                self.video_urls.append(src)

    def handle_data(self, data: str) -> None:
        value = " ".join(data.split()).strip()
        if value:
            self.text.append(value)


class ThreadsOEmbedDetailAdapter:
    backend_name = "threads_oembed_detail"
    backend_version = "official-oembed-v1"

    def __init__(self, json_loader: Callable[[str, dict[str, str]], dict[str, Any]] | None = None):
        self._json_loader = json_loader or _json_get

    def fetch_url(self, source: dict[str, Any], post_url: str) -> ProviderResult[NormalizedSourcePost]:
        canonical_post = canonical_threads_post_url(post_url)
        if not canonical_post:
            return ProviderResult(self.backend_name, self.backend_version, "BLOCKED", reason="threads_individual_post_url_required")
        expected = threads_handle(str(source.get("source_url") or ""))
        url_handle = threads_handle(canonical_post)
        if expected and url_handle and expected != url_handle:
            return ProviderResult(self.backend_name, self.backend_version, "BLOCKED", reason="threads_author_mismatch")
        endpoint = f"{OEMBED_ENDPOINT}?{urlencode({'url': canonical_post, 'omitscript': 'true'})}"
        try:
            payload = self._json_loader(endpoint, {"Accept": "application/json"})
            author_url = canonical_url(str(payload.get("author_url") or ""))
            author = threads_handle(author_url) or url_handle
            author_name_handle = str(payload.get("author_name") or "").lower().lstrip("@")
            if not author and author_name_handle == expected:
                author = author_name_handle
            if expected and author and author != expected:
                raise ValueError("threads_author_mismatch")
            if expected and not author and not url_handle:
                raise ValueError("threads_author_unverified")
            parser = _EmbedParser()
            parser.feed(str(payload.get("html") or ""))
            text = str(payload.get("title") or "").strip() or " ".join(parser.text).strip()
            source_id = str(source.get("source_id") or "")
            external = external_post_id(canonical_post)
            source_post_id = f"sp_{source_id}_{external}"
            media = tuple(
                NormalizedMediaItem(
                    source_post_media_id=f"spm_{source_post_id}_{index}",
                    source_post_id=source_post_id,
                    media_index=index,
                    media_type="video",
                    canonical_post_url=canonical_post,
                    original_media_url=canonical_url(media_url),
                    resolver_backend=self.backend_name,
                )
                for index, media_url in enumerate(parser.video_urls)
            )
            post = NormalizedSourcePost(
                source_post_id=source_post_id,
                source_id=source_id,
                target_account_id=_target_account(source),
                platform="threads",
                profile_url=canonical_url(str(source.get("source_url") or author_url)),
                canonical_post_url=canonical_post,
                external_post_id=external,
                original_post_text=html.unescape(text),
                published_at="",
                author_name=str(payload.get("author_name") or ""),
                author_handle=author,
                media_items=media,
                engagement={},
                collection_backend=self.backend_name,
                backend_version=self.backend_version,
                content_hash=stable_content_hash(text, [item.original_media_url for item in media]),
                discovered_at=utc_now(),
                detail_status="PASS" if text else "PARTIAL",
            )
            return ProviderResult(self.backend_name, self.backend_version, "PASS" if text else "PARTIAL", data=post)
        except Exception as exc:
            return ProviderResult(self.backend_name, self.backend_version, "FAILED", reason=str(exc) or type(exc).__name__, retryable=True)

    def discover_profile(self, source: dict[str, Any], *, limit: int) -> ProviderResult[list[NormalizedSourcePost]]:
        post_url = str(source.get("canonical_post_url") or source.get("post_url") or source.get("source_url") or "")
        result = self.fetch_url(source, post_url)
        return ProviderResult(
            self.backend_name,
            self.backend_version,
            result.status,
            data=[result.data] if result.data else [],
            reason=result.reason,
            retryable=result.retryable,
        )
