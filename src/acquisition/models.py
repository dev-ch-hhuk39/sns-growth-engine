"""Shared normalized records for source acquisition.

The source post is the ownership boundary for direct-media reuse: every media
item carries the exact parent ``source_post_id`` and canonical post URL.  This
prevents a caption from one source post being combined with media from another.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_url(url: str) -> str:
    """Normalize tracking URLs without losing a platform's post identity."""
    parsed = urlsplit(str(url or "").strip())
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    pairs = parse_qsl(parsed.query, keep_blank_values=False)
    if "youtube" in host and path == "/watch":
        pairs = [(key, value) for key, value in pairs if key == "v" and value]
    elif "threads" in host or "tiktok" in host:
        pairs = []
    return urlunsplit((parsed.scheme or "https", host, path, urlencode(pairs), ""))


def external_post_id(url: str, fallback: str = "") -> str:
    """Return a stable platform ID, with a canonical URL hash as a fallback."""
    normalized = canonical_url(url)
    patterns = (
        r"/post/([A-Za-z0-9_-]+)",
        r"/video/(\d+)",
        r"[?&]v=([A-Za-z0-9_-]{6,})",
        r"/shorts/([A-Za-z0-9_-]{6,})",
    )
    for pattern in patterns:
        match = re.search(pattern, normalized)
        if match:
            return match.group(1)
    return fallback or hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:20]


def stable_content_hash(text: str, media_urls: list[str]) -> str:
    payload = json.dumps(
        {"text": str(text or "").strip(), "media": [canonical_url(url) for url in media_urls]},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceAccount:
    """One configured source account and its immutable targeting boundary."""

    source_id: str
    source_url: str
    platform: str
    source_type: str
    target_account_id: str
    rights_status: str
    permission_status: str
    active: bool = False
    fetch_enabled: bool = False
    manual_only: bool = True

    @classmethod
    def from_mapping(cls, row: dict[str, Any]) -> "SourceAccount":
        targets = row.get("target_account_ids") or [row.get("target_account_id", "")]
        return cls(
            source_id=str(row.get("source_id", "")),
            source_url=canonical_url(str(row.get("source_url", ""))),
            platform=str(row.get("source_platform") or row.get("platform") or "").lower(),
            source_type=str(row.get("source_type") or "account").lower(),
            target_account_id=str(targets[0] if targets else ""),
            rights_status=str(row.get("rights_status") or row.get("rights_policy") or "unknown").lower(),
            permission_status=str(row.get("permission_status") or "unknown").lower(),
            active=row.get("active") is True or str(row.get("active", "")).lower() == "true",
            fetch_enabled=row.get("fetch_enabled") is True or str(row.get("fetch_enabled", "")).lower() == "true",
            manual_only=not (row.get("manual_only") is False or str(row.get("manual_only", "")).lower() == "false"),
        )


@dataclass(frozen=True)
class NormalizedMediaItem:
    source_post_media_id: str
    source_post_id: str
    media_index: int
    media_type: str
    canonical_post_url: str
    original_media_url: str
    resolver_backend: str
    mime_type: str = ""
    width: str = ""
    height: str = ""
    duration_seconds: str = ""
    thumbnail_url: str = ""
    content_hash: str = ""
    download_status: str = "PENDING"
    cloudinary_status: str = "PENDING"
    storage_url: str = ""

    def to_sheet_row(self, *, rights_status: str, permission_status: str) -> dict[str, str]:
        now = utc_now()
        ratio = ""
        if self.width and self.height:
            try:
                ratio = "9:16" if int(self.height) > int(self.width) else ""
            except ValueError:
                pass
        return {
            "source_post_media_id": self.source_post_media_id,
            "source_post_id": self.source_post_id,
            "media_index": str(self.media_index),
            "original_media_url": self.original_media_url,
            "canonical_post_url": self.canonical_post_url,
            "acquisition_method": self.resolver_backend,
            "resolver_backend": self.resolver_backend,
            "thumbnail_url": self.thumbnail_url,
            "media_type": self.media_type,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "aspect_ratio": ratio,
            "duration_seconds": self.duration_seconds,
            "content_hash": self.content_hash,
            "download_status": self.download_status,
            "cloudinary_status": self.cloudinary_status,
            "storage_url": self.storage_url,
            "rights_status": rights_status,
            "permission_status": permission_status,
            "reuse_status": "APPROVED",
            "retry_count": "0",
            "last_error": "",
            "failure_signature": "",
            "same_failure_count": "0",
            "last_attempt_at": "",
            "quarantined_at": "",
            "quarantine_reason": "",
            "created_at": now,
            "updated_at": now,
        }


@dataclass(frozen=True)
class NormalizedSourcePost:
    source_post_id: str
    source_id: str
    target_account_id: str
    platform: str
    profile_url: str
    canonical_post_url: str
    external_post_id: str
    original_post_text: str
    published_at: str
    author_name: str = ""
    author_handle: str = ""
    media_items: tuple[NormalizedMediaItem, ...] = field(default_factory=tuple)
    engagement: dict[str, Any] = field(default_factory=dict)
    collection_backend: str = ""
    backend_version: str = ""
    content_hash: str = ""
    discovered_at: str = ""
    comments: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    detail_status: str = "PARTIAL"

    @property
    def media_count(self) -> int:
        return len(self.media_items)

    @property
    def media_type(self) -> str:
        kinds = {item.media_type for item in self.media_items}
        if not kinds:
            return ""
        if len(kinds) == 1:
            return next(iter(kinds))
        return "mixed_carousel"

    def to_sheet_row(self, *, rights_status: str, permission_status: str) -> dict[str, str]:
        now = utc_now()
        return {
            "source_post_id": self.source_post_id,
            "source_id": self.source_id,
            "source_account_id": self.source_id,
            "target_account_id": self.target_account_id,
            "platform": self.platform,
            "profile_url": self.profile_url,
            "canonical_post_url": self.canonical_post_url,
            "external_post_id": self.external_post_id,
            "original_post_text": self.original_post_text,
            "published_at": self.published_at,
            "author_name": self.author_name,
            "author_handle": self.author_handle,
            "media_count": str(self.media_count),
            "media_type": self.media_type,
            "media_items_json": json.dumps([asdict(item) for item in self.media_items], ensure_ascii=False),
            "engagement_json": json.dumps(self.engagement, ensure_ascii=False, sort_keys=True),
            "comments_json": json.dumps(list(self.comments), ensure_ascii=False),
            "comment_count_collected": str(len(self.comments)),
            "detail_status": self.detail_status,
            "collection_backend": self.collection_backend,
            "backend_version": self.backend_version,
            "rights_status": rights_status,
            "permission_status": permission_status,
            "permission_scope": "owner_attestation",
            "attribution_policy": "internal_ledger",
            "direct_media_reuse_allowed": "true",
            "collection_status": "DISCOVERED",
            "processing_status": "PENDING",
            "content_hash": self.content_hash,
            "retry_count": "0",
            "last_error": "",
            "failure_signature": "",
            "same_failure_count": "0",
            "last_attempt_at": "",
            "quarantined_at": "",
            "quarantine_reason": "",
            "created_at": now,
            "updated_at": now,
        }


def validate_source_post(post: NormalizedSourcePost) -> list[str]:
    errors: list[str] = []
    if not post.source_post_id or not post.source_id or not post.target_account_id:
        errors.append("missing_identity")
    if post.platform not in {"threads", "tiktok", "youtube"}:
        errors.append("unsupported_platform")
    if not post.canonical_post_url.startswith("https://"):
        errors.append("canonical_post_url_required")
    if not post.external_post_id:
        errors.append("external_post_id_required")
    seen: set[str] = set()
    for item in post.media_items:
        if item.source_post_id != post.source_post_id:
            errors.append("cross_post_media_link")
        if item.media_index < 0 or item.media_index in seen:
            errors.append("invalid_or_duplicate_media_index")
        seen.add(item.media_index)
        if item.media_type not in {"image", "video"}:
            errors.append("unsupported_media_type")
        if not item.original_media_url.startswith("https://"):
            errors.append("media_url_required")
    return sorted(set(errors))


# Public names used by the capability contracts.  The aliases preserve every
# existing adapter import while making the ownership model explicit.
SourceMediaItem = NormalizedMediaItem
SourcePostBundle = NormalizedSourcePost
