"""Bounded X profile discovery through the project's gallery-dl backend.

This adapter is intentionally metadata-only.  It invokes gallery-dl in JSON
dump mode for an explicitly approved profile, normalizes only individual
``/status/<id>`` posts, and never passes browser cookies, downloads media, or
publishes to X.  The caller still needs the separate permission ledger before
any discovered media can enter a direct-media pipeline.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import defaultdict
from typing import Any

from .models import (
    NormalizedMediaItem,
    NormalizedSourcePost,
    canonical_url,
    external_post_id,
    stable_content_hash,
    utc_now,
)
from .router import BackendFailure

MAX_X_PROFILE_POSTS = 20
X_PROFILE = re.compile(r"^https://(?:www\.)?(?:x|twitter)\.com/(?P<handle>[A-Za-z0-9_]+)$", re.I)
X_STATUS = re.compile(r"https?://(?:www\.)?(?:x|twitter)\.com/[A-Za-z0-9_]+/status/\d+", re.I)


def _truthy(value: Any) -> bool:
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}


def _account_id(source: dict[str, Any]) -> str:
    targets = source.get("target_account_ids") or [source.get("target_account_id")]
    return str(targets[0] if targets else "")


def _profile_url(source: dict[str, Any]) -> str:
    url = canonical_url(str(source.get("canonical_url") or source.get("source_url") or ""))
    if X_PROFILE.match(url):
        return url
    handle = str(source.get("source_handle") or source.get("handle") or "").strip().lstrip("@")
    return f"https://x.com/{handle}" if re.fullmatch(r"[A-Za-z0-9_]+", handle) else ""


def _field(item: dict[str, Any], *names: str) -> str:
    for name in names:
        value = item.get(name)
        if value not in (None, ""):
            return str(value)
    return ""


def _post_url(item: dict[str, Any]) -> str:
    for value in item.values():
        if isinstance(value, str):
            match = X_STATUS.search(value)
            if match:
                return canonical_url(match.group(0))
    return ""


class XGalleryDlProfileAdapter:
    backend_name = "x_gallery_dl"
    backend_version = "gallery-dl-bounded-json"

    def _command(self, profile_url: str, *, limit: int) -> list[str]:
        # --dump-json emits extraction metadata only.  Do not add cookie,
        # browser, username, password, output, or download switches here.
        return ["gallery-dl", "--dump-json", "--range", f"1-{limit}", profile_url]

    def acquire(self, source: dict[str, Any], *, limit: int) -> list[NormalizedSourcePost]:
        if not _truthy(source.get("x_read_only")):
            raise BackendFailure("x_read_only_not_approved")
        profile_url = _profile_url(source)
        if not profile_url:
            raise BackendFailure("x_profile_handle_required")
        if shutil.which("gallery-dl") is None:
            raise BackendFailure("gallery_dl_not_installed_browser_export_or_manual_json_required")
        bounded = max(1, min(int(limit), MAX_X_PROFILE_POSTS))
        try:
            completed = subprocess.run(
                self._command(profile_url, limit=bounded),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=90,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise BackendFailure(f"gallery_dl_x_profile_failed:{type(exc).__name__}") from exc
        if completed.returncode:
            raise BackendFailure(f"gallery_dl_x_profile_failed:exit_{completed.returncode}")

        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for line in completed.stdout.splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(row, dict):
                continue
            post_url = _post_url(row)
            if post_url:
                grouped[post_url].append(row)

        account_id = _account_id(source)
        posts: list[NormalizedSourcePost] = []
        for post_url, rows in list(grouped.items())[:bounded]:
            first = rows[0]
            post_external_id = external_post_id(post_url, _field(first, "tweet_id", "tweetId", "id"))
            post_id = f"sp_{source.get('source_id', '')}_{post_external_id}"
            media_items: list[NormalizedMediaItem] = []
            for index, row in enumerate(rows):
                media_url = _field(row, "url", "media_url", "image_url")
                if not media_url.startswith("https://"):
                    continue
                media_type = "video" if _field(row, "extension", "filename").lower().endswith((".mp4", ".webm", ".mov")) else "image"
                media_items.append(NormalizedMediaItem(
                    source_post_media_id=f"spm_{post_id}_{index}",
                    source_post_id=post_id,
                    media_index=index,
                    media_type=media_type,
                    canonical_post_url=post_url,
                    original_media_url=media_url,
                    resolver_backend=self.backend_name,
                    thumbnail_url=_field(row, "thumbnail", "preview_image_url"),
                ))
            text = _field(first, "tweet_content", "tweet_text", "content", "text", "description")
            posts.append(NormalizedSourcePost(
                source_post_id=post_id,
                source_id=str(source.get("source_id", "")),
                target_account_id=account_id,
                platform="x",
                profile_url=profile_url,
                canonical_post_url=post_url,
                external_post_id=post_external_id,
                original_post_text=text,
                published_at=_field(first, "date", "created_at", "tweet_date"),
                author_handle=_field(first, "author", "user", "username") or profile_url.rsplit("/", 1)[-1],
                media_items=tuple(media_items),
                collection_backend=self.backend_name,
                backend_version=self.backend_version,
                content_hash=stable_content_hash(text, [item.original_media_url for item in media_items]),
                discovered_at=utc_now(),
            ))
        if not posts:
            raise BackendFailure("x_gallery_dl_individual_posts_unavailable_browser_export_or_manual_json_required")
        return posts
