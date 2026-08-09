"""Bounded gallery-dl fallback for approved TikTok profile discovery.

It performs JSON metadata extraction only. Downloading stays in the separately
gated individual-video runner after rights and permission validation.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import defaultdict
from typing import Any

from .models import NormalizedMediaItem, NormalizedSourcePost, canonical_url, external_post_id, stable_content_hash, utc_now
from .router import BackendFailure

MAX_TIKTOK_PROFILE_POSTS = 20
PROFILE = re.compile(r"^https://(?:www\.)?tiktok\.com/@(?P<handle>[A-Za-z0-9._-]+)$", re.I)
VIDEO = re.compile(r"https?://(?:www\.)?tiktok\.com/@[A-Za-z0-9._-]+/video/\d+", re.I)


def _true(value: Any) -> bool:
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}


class TikTokGalleryDlProfileAdapter:
    backend_name = "tiktok_gallery_dl"
    backend_version = "gallery-dl-bounded-json"

    def acquire(self, source: dict[str, Any], *, limit: int) -> list[NormalizedSourcePost]:
        if str(source.get("source_platform") or source.get("platform") or "").lower() != "tiktok":
            raise BackendFailure("tiktok_gallery_dl_unsupported_platform")
        if not _true(source.get("fetch_enabled", True)):
            raise BackendFailure("tiktok_gallery_dl_source_not_fetch_enabled")
        profile_url = canonical_url(str(source.get("canonical_url") or source.get("source_url") or ""))
        if not PROFILE.match(profile_url):
            raise BackendFailure("tiktok_profile_url_required")
        if shutil.which("gallery-dl") is None:
            raise BackendFailure("gallery_dl_not_installed")
        bounded = max(1, min(int(limit), MAX_TIKTOK_PROFILE_POSTS))
        try:
            completed = subprocess.run(["gallery-dl", "--dump-json", "--range", f"1-{bounded}", profile_url], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=90)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BackendFailure(f"tiktok_gallery_dl_failed:{type(exc).__name__}") from exc
        if completed.returncode:
            raise BackendFailure(f"tiktok_gallery_dl_failed:exit_{completed.returncode}")
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for line in completed.stdout.splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            post_url = next((canonical_url(value.group(0)) for value in (VIDEO.search(str(item)) for item in row.values() if isinstance(item, str)) if value), "")
            if post_url:
                grouped[post_url].append(row)
        account = str((source.get("target_account_ids") or [source.get("target_account_id")])[0] or "")
        posts = []
        for post_url, rows in list(grouped.items())[:bounded]:
            first = rows[0]; post_id = external_post_id(post_url); parent_id = f"sp_{source.get('source_id', '')}_{post_id}"
            media = []
            for index, row in enumerate(rows):
                url = str(row.get("url") or row.get("media_url") or "")
                if url.startswith("https://"):
                    media.append(NormalizedMediaItem(f"spm_{parent_id}_{index}", parent_id, index, "video", post_url, url, self.backend_name))
            text = str(first.get("description") or first.get("text") or first.get("title") or "")
            posts.append(NormalizedSourcePost(parent_id, str(source.get("source_id", "")), account, "tiktok", profile_url, post_url, post_id, text, str(first.get("date") or ""), author_handle=profile_url.rsplit("@", 1)[-1], media_items=tuple(media), collection_backend=self.backend_name, backend_version=self.backend_version, content_hash=stable_content_hash(text, [item.original_media_url for item in media]), discovered_at=utc_now()))
        if not posts:
            raise BackendFailure("tiktok_gallery_dl_individual_posts_unavailable")
        return posts
