"""Bounded public metadata, comments and transcript providers."""
from __future__ import annotations

import json
import re
import time
from dataclasses import replace
from itertools import islice
from typing import Any, Callable
from urllib.request import Request, urlopen

from .contracts import ProviderResult
from .models import SourceMediaItem, SourcePostBundle, stable_content_hash


class YouTubeTranscriptProvider:
    provider_name = "youtube_transcript_api"
    provider_version = "1.2.4"

    def fetch_transcript(self, post: SourcePostBundle) -> ProviderResult[dict[str, Any]]:
        if post.platform != "youtube" or not post.external_post_id:
            return ProviderResult(self.provider_name, self.provider_version, "BLOCKED", reason="youtube_video_id_required")
        started = time.monotonic()
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            api = YouTubeTranscriptApi()
            fetched = api.fetch(post.external_post_id, languages=["ja", "en"])
            segments = [
                {"text": str(item.text), "start": float(item.start), "duration": float(item.duration)}
                for item in fetched
            ]
            text = " ".join(item["text"] for item in segments).strip()
            status = "PASS" if text else "PARTIAL"
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                status,
                data={
                    "video_id": post.external_post_id,
                    "language": getattr(fetched, "language_code", ""),
                    "is_generated": bool(getattr(fetched, "is_generated", False)),
                    "text": text,
                    "segments": segments,
                },
                reason="" if text else "empty_transcript",
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                "UNAVAILABLE",
                reason=f"{type(exc).__name__}:youtube_transcript_unavailable",
                retryable=False,
                duration_ms=int((time.monotonic() - started) * 1000),
            )


class YouTubeCommentProvider:
    provider_name = "youtube_comment_downloader"
    provider_version = "0.1.78"

    def fetch_comments(self, post: SourcePostBundle, *, limit: int) -> ProviderResult[list[dict[str, Any]]]:
        if post.platform != "youtube" or not post.canonical_post_url:
            return ProviderResult(self.provider_name, self.provider_version, "BLOCKED", reason="youtube_post_url_required")
        bounded_limit = max(0, min(int(limit), 100))
        try:
            from youtube_comment_downloader import SORT_BY_POPULAR, YoutubeCommentDownloader

            downloader = YoutubeCommentDownloader()
            raw = downloader.get_comments_from_url(post.canonical_post_url, sort_by=SORT_BY_POPULAR)
            rows = []
            for item in islice(raw, bounded_limit):
                text = str(item.get("text", "")).strip()
                if not text:
                    continue
                rows.append({
                    "comment_id": str(item.get("cid", "")),
                    "text": text[:2000],
                    "author": str(item.get("author", ""))[:160],
                    "like_count": item.get("votes", ""),
                    "published_label": str(item.get("time", ""))[:120],
                    "is_reply": bool(item.get("reply")),
                })
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                "PASS" if rows else "PARTIAL",
                data=rows,
                reason="" if rows else "no_public_comments",
                metadata={"limit": bounded_limit},
            )
        except ImportError:
            return ProviderResult(self.provider_name, self.provider_version, "UNAVAILABLE", reason="youtube_comment_downloader_not_installed")
        except Exception as exc:
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                "UNAVAILABLE",
                reason=f"{type(exc).__name__}:youtube_comments_unavailable",
                retryable=True,
                metadata={"limit": bounded_limit},
            )


def _walk_json(value: Any):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_json(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_json(nested)


def extract_threads_comments(page_html: str, source_text: str, *, limit: int) -> list[dict[str, Any]]:
    """Extract only public reply objects embedded in a post page.

    Threads changes its JSON shape frequently, so the parser accepts several
    documented-looking field variants but requires both text and an author-like
    field.  It never calls private GraphQL endpoints or reads browser state.
    """
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", page_html, flags=re.I | re.S)
    source_compact = re.sub(r"\s+", "", source_text)
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for script in scripts:
        candidate = script.strip()
        if not candidate or candidate[0] not in "[{":
            continue
        try:
            payload = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        for item in _walk_json(payload):
            text = str(item.get("text") or item.get("caption") or "").strip()
            user = item.get("user") or item.get("owner") or item.get("author")
            author = ""
            if isinstance(user, dict):
                author = str(user.get("username") or user.get("handle") or user.get("name") or "")
            elif user:
                author = str(user)
            compact = re.sub(r"\s+", "", text)
            if not text or not author or compact == source_compact:
                continue
            comment_id = str(item.get("pk") or item.get("id") or item.get("code") or "")
            key = comment_id or stable_content_hash(text, [])
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "comment_id": comment_id,
                "text": text[:2000],
                "author": author[:160],
                "like_count": item.get("like_count", ""),
                "published_at": str(item.get("taken_at") or item.get("created_at") or ""),
            })
            if len(rows) >= limit:
                return rows
    return rows


class ThreadsPublicCommentProvider:
    provider_name = "threads_public_embedded_json"
    provider_version = "1"

    def __init__(self, html_loader: Callable[[str], str] | None = None):
        self._html_loader = html_loader

    def _load(self, url: str) -> str:
        if self._html_loader:
            return self._html_loader(url)
        request = Request(url, headers={"User-Agent": "SNSGrowthEngine/1.0 public-comment-reader"})
        with urlopen(request, timeout=20) as response:
            return response.read(3_000_000).decode("utf-8", errors="replace")

    def fetch_comments(self, post: SourcePostBundle, *, limit: int) -> ProviderResult[list[dict[str, Any]]]:
        if post.platform != "threads":
            return ProviderResult(self.provider_name, self.provider_version, "BLOCKED", reason="threads_post_required")
        bounded_limit = max(0, min(int(limit), 50))
        try:
            rows = extract_threads_comments(self._load(post.canonical_post_url), post.original_post_text, limit=bounded_limit)
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                "PASS" if rows else "PARTIAL",
                data=rows,
                reason="" if rows else "public_replies_not_embedded",
                metadata={"limit": bounded_limit},
            )
        except Exception as exc:
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                "UNAVAILABLE",
                reason=f"{type(exc).__name__}:threads_comments_unavailable",
                retryable=True,
                metadata={"limit": bounded_limit},
            )


class YtDlpPostDetailProvider:
    provider_name = "yt_dlp_post_detail"
    provider_version = "2026.7.4"

    def fetch_post_detail(self, post: SourcePostBundle) -> ProviderResult[SourcePostBundle]:
        if post.platform not in {"youtube", "tiktok"}:
            return ProviderResult(self.provider_name, self.provider_version, "BLOCKED", reason="video_platform_required")
        try:
            import yt_dlp

            options = {"quiet": True, "skip_download": True, "noplaylist": True, "writesubtitles": False}
            info = yt_dlp.YoutubeDL(options).extract_info(post.canonical_post_url, download=False)
            if not isinstance(info, dict):
                return ProviderResult(self.provider_name, self.provider_version, "FAILED", reason="metadata_response_invalid")
            text = str(info.get("description") or info.get("title") or post.original_post_text)
            media = tuple(
                replace(
                    item,
                    duration_seconds=str(info.get("duration") or item.duration_seconds),
                    width=str(info.get("width") or item.width),
                    height=str(info.get("height") or item.height),
                    thumbnail_url=str(info.get("thumbnail") or item.thumbnail_url),
                )
                for item in post.media_items
            )
            detailed = replace(
                post,
                original_post_text=text,
                media_items=media,
                engagement={
                    key: info.get(key)
                    for key in ("view_count", "like_count", "comment_count")
                    if info.get(key) is not None
                },
                detail_status="COMPLETE",
                content_hash=stable_content_hash(text, [item.original_media_url for item in media]),
            )
            return ProviderResult(self.provider_name, self.provider_version, "PASS", data=detailed)
        except Exception as exc:
            return ProviderResult(
                self.provider_name,
                self.provider_version,
                "UNAVAILABLE",
                reason=f"{type(exc).__name__}:video_detail_unavailable",
                retryable=True,
            )


class FirecrawlWebEnrichmentProvider:
    """Optional HTTP endpoint; never a mandatory paid dependency."""

    provider_name = "firecrawl_optional"
    provider_version = "47f321f1"

    def enrich(self, post: SourcePostBundle) -> ProviderResult[SourcePostBundle]:
        return ProviderResult(
            self.provider_name,
            self.provider_version,
            "UNAVAILABLE",
            reason="optional_web_enrichment_not_configured",
            retryable=False,
        )
