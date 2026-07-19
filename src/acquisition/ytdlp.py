"""yt-dlp PRIMARY adapter for public YouTube/TikTok profile discovery."""
from __future__ import annotations

import hashlib
from typing import Any

from .contracts import ProviderResult
from .models import NormalizedMediaItem, NormalizedSourcePost, canonical_url, external_post_id, stable_content_hash, utc_now
from .router import BackendFailure


class YtDlpProfilePostAdapter:
    backend_name = "yt_dlp"
    backend_version = "python-module"

    def acquire(self, source: dict[str, Any], *, limit: int) -> list[NormalizedSourcePost]:
        try:
            import yt_dlp
        except ImportError as exc:
            raise BackendFailure("yt_dlp_not_installed") from exc
        platform = str(source.get("source_platform") or source.get("platform") or "").lower()
        if platform not in {"youtube", "tiktok"}:
            raise BackendFailure(f"yt_dlp_unsupported_platform:{platform}")
        source_url = str(source.get("canonical_url") or source.get("source_url") or "").rstrip("/")
        if platform == "youtube" and "/channel/" in source_url and not source_url.endswith("/videos"):
            source_url = f"{source_url}/videos"
        options = {
            "quiet": True,
            "skip_download": True,
            "extract_flat": True,
            "playlistend": max(1, min(limit, 20)),
            "js_runtimes": {"node": {}},
        }
        try:
            info = yt_dlp.YoutubeDL(options).extract_info(source_url, download=False)
        except Exception as exc:
            raise BackendFailure(f"yt_dlp_discovery_failed:{type(exc).__name__}") from exc
        entries = info.get("entries") if isinstance(info, dict) else None
        entries = entries if isinstance(entries, list) else [info]
        account_id = str((source.get("target_account_ids") or [source.get("target_account_id")])[0] or "")
        result: list[NormalizedSourcePost] = []
        for entry in entries[:limit]:
            if not isinstance(entry, dict):
                continue
            raw_url = str(entry.get("webpage_url") or entry.get("url") or "")
            if not raw_url.startswith("https://"):
                continue
            post_url = canonical_url(raw_url)
            if platform == "youtube" and not ("/watch" in post_url or "/shorts/" in post_url):
                continue
            if platform == "tiktok" and "/video/" not in post_url:
                continue
            post_external_id = str(entry.get("id") or external_post_id(post_url))
            post_id = f"sp_{source['source_id']}_{post_external_id}"
            duration = str(entry.get("duration") or "")
            media = NormalizedMediaItem(
                source_post_media_id=f"spm_{post_id}_0",
                source_post_id=post_id,
                media_index=0,
                media_type="video",
                canonical_post_url=post_url,
                original_media_url=post_url,
                resolver_backend=self.backend_name,
                duration_seconds=duration,
                thumbnail_url=str(entry.get("thumbnail") or ""),
            )
            text = str(entry.get("description") or entry.get("title") or "")
            result.append(NormalizedSourcePost(
                source_post_id=post_id,
                source_id=str(source["source_id"]),
                target_account_id=account_id,
                platform=platform,
                profile_url=canonical_url(str(source.get("source_url") or "")),
                canonical_post_url=post_url,
                external_post_id=post_external_id,
                original_post_text=text,
                published_at=str(entry.get("upload_date") or entry.get("timestamp") or ""),
                author_name=str(entry.get("uploader") or ""),
                author_handle=str(entry.get("channel_id") or entry.get("uploader_id") or ""),
                media_items=(media,),
                engagement={key: entry.get(key) for key in ("view_count", "like_count", "comment_count") if entry.get(key) is not None},
                collection_backend=self.backend_name,
                backend_version=self.backend_version,
                content_hash=stable_content_hash(text, [post_url]),
                discovered_at=utc_now(),
            ))
        return result

    def discover_profile(self, source: dict[str, Any], *, limit: int) -> ProviderResult[list[NormalizedSourcePost]]:
        try:
            posts = self.acquire(source, limit=limit)
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                "PASS" if posts else "PARTIAL",
                data=posts,
                reason="" if posts else "no_videos_discovered",
            )
        except Exception as exc:
            return ProviderResult(
                self.backend_name,
                self.backend_version,
                "FAILED",
                reason=f"{type(exc).__name__}:profile_discovery_failed",
                retryable=True,
            )
