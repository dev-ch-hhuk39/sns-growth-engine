"""Canonical and provenance checks for owner-approved exact X status URLs."""
from __future__ import annotations

import re
from typing import Any

STATUS_RE = re.compile(
    r"^https?://(?:www\.)?(?:x|twitter)\.com/([A-Za-z0-9_]+)/status/(\d+)(?:[/?#].*)?$",
    re.I,
)


def canonical_x_status_url(url: str) -> str:
    match = STATUS_RE.match(str(url or "").strip())
    if not match:
        return ""
    return f"https://x.com/{match.group(1)}/status/{match.group(2)}"


def x_status_identity(url: str) -> tuple[str, str]:
    match = STATUS_RE.match(str(url or "").strip())
    return (match.group(1).lower(), match.group(2)) if match else ("", "")


def validate_exact_status_provenance(
    url: str, registered_source: dict[str, Any], metadata: dict[str, Any]
) -> dict[str, Any]:
    """Fail closed on profile URLs, author mismatch, retweets, and quotes."""
    handle, status_id = x_status_identity(url)
    expected = str(
        registered_source.get("source_handle")
        or registered_source.get("author_handle")
        or ""
    ).strip().lstrip("@").lower()
    metadata_author = str(
        metadata.get("uploader_id")
        or metadata.get("channel_id")
        or metadata.get("author_handle")
        or ""
    ).strip().lstrip("@").lower()
    metadata_status_id = str(metadata.get("display_id") or "").strip()
    metadata_page_handle, metadata_page_status_id = x_status_identity(
        str(metadata.get("webpage_url") or metadata.get("original_url") or "")
    )
    reasons: list[str] = []
    if not status_id:
        reasons.append("individual_x_status_url_required")
    if not expected or handle != expected:
        reasons.append("registered_source_handle_mismatch")
    if metadata_author and metadata_author != expected:
        reasons.append("extracted_author_mismatch")
    if metadata_status_id and metadata_status_id != status_id:
        reasons.append("extracted_status_id_mismatch")
    if metadata_page_status_id and metadata_page_status_id != status_id:
        reasons.append("extracted_webpage_status_id_mismatch")
    if metadata_page_handle and metadata_page_handle != expected:
        reasons.append("extracted_webpage_author_mismatch")
    repost_fields = (
        "is_retweet",
        "retweeted_status",
        "retweeted_status_id",
        "is_quote_status",
        "quoted_status",
        "quoted_status_id",
    )
    if any(metadata.get(field) not in (None, False, "", 0, "0", "false") for field in repost_fields):
        reasons.append("retweet_or_quote_not_eligible")
    formats = metadata.get("formats") or []
    has_video = any(
        str(row.get("vcodec") or "none").lower() != "none"
        for row in formats
        if isinstance(row, dict)
    )
    if not has_video:
        reasons.append("no_video")
    return {
        "status": "PASS" if not reasons else "BLOCKED",
        "canonical_url": canonical_x_status_url(url),
        "registered_handle": f"@{expected}" if expected else "",
        "extracted_author": f"@{metadata_author}" if metadata_author else "",
        "external_post_id": status_id,
        "extracted_display_id": metadata_status_id,
        "downloaded_media_id": str(metadata.get("id") or ""),
        "is_registered_author_post": not any(
            reason.endswith("author_mismatch") or reason == "registered_source_handle_mismatch"
            for reason in reasons
        ),
        "is_retweet_or_quote": "retweet_or_quote_not_eligible" in reasons,
        "has_video": has_video,
        "reasons": reasons,
    }
