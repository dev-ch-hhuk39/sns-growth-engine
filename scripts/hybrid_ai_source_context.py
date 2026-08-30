#!/usr/bin/env python3
"""Resolve and hash source evidence used by the Hybrid Gemini gate.

Optional legacy tabs are fail-soft. Explicit source IDs, clip IDs and video IDs
remain fail-closed. Media reuse requires a live permission-ledger record; queue
labels alone never create permission.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from sheets_record_reader import read_records_safely
from accounts.managed_accounts import managed_account_ids

TARGET_ACCOUNTS = set(managed_account_ids())
SOURCE_HASH_FIELDS = (
    "source_post_id", "source_video_id", "clip_candidate_id", "source_id",
    "source_result_id", "original_post_text", "transcript_excerpt",
    "transcript", "description", "source_text", "use_policy",
    "usage_scope", "reuse_policy", "source_target_account_id",
    "permission_evidence_status", "clip_duration_seconds",
    "clip_start_seconds", "clip_end_seconds", "canonical_source_url",
    "source_author_identity_status", "source_parent_identity_status",
    "source_media_parent_status", "source_media_order_status",
    "provenance_status", "read_errors",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _claim_support_evidence(value: Any) -> str:
    """Extract public source evidence without leaking the private JSON packet."""
    raw = _text(value)
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return ""
    rows = parsed if isinstance(parsed, list) else [parsed]
    evidence: list[str] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        text = _text(row.get("source_evidence"))
        if text and text not in evidence:
            evidence.append(text)
    return "\n\n".join(evidence)


def _true(value: Any) -> bool:
    return _text(value).lower() in {"1", "true", "yes", "y", "approved", "granted"}


def _read(client: Any, logical: str, errors: list[str], *, required: bool = False) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in read_records_safely(client, logical)]
    except Exception as exc:
        if required:
            errors.append(f"{logical}:{type(exc).__name__}")
        return []


def _lookup(rows: list[dict[str, Any]], keys: tuple[str, ...], value: str) -> dict[str, Any]:
    if not value:
        return {}
    for row in rows:
        if any(_text(row.get(key)) == value for key in keys):
            return row
    return {}


def _target_account(*rows: Mapping[str, Any]) -> str:
    for row in rows:
        explicit = _first(row.get("target_account_id"), row.get("destination_account_id"), row.get("target_account"))
        if explicit:
            return explicit
        account_id = _text(row.get("account_id"))
        if account_id in TARGET_ACCOUNTS:
            return account_id
    return ""


def _permission_is_current(row: Mapping[str, Any]) -> bool:
    if not row or _true(row.get("revoked")):
        return False
    expires = _text(row.get("expires_at"))
    if expires:
        try:
            parsed = datetime.fromisoformat(expires.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed < datetime.now(timezone.utc):
                return False
        except ValueError:
            return False
    return bool(_text(row.get("evidence_type")) and _text(row.get("evidence_reference")))


def _media_permission_status(queue: Mapping[str, Any], permission: Mapping[str, Any]) -> str:
    origin = _text(queue.get("media_origin")).lower()
    content_type = _text(queue.get("content_type")).lower()
    mode = _text(queue.get("generation_mode")).lower()
    media_route = bool(origin or content_type in {"direct_reference_media", "approved_source_clip"} or mode in {"direct_reference_media", "saved_direct_reference_media", "saved_approved_source_clip", "approved_source_clip"})
    if not media_route:
        return "NOT_REQUIRED"
    ownership = _first(queue.get("ownership"), queue.get("source_ownership")).lower()
    rights = _text(queue.get("rights_status")).lower()
    if ownership in {"owned", "system_owned"} or rights in {"owned", "licensed"}:
        return "APPROVED"
    if not _permission_is_current(permission):
        return "MISSING"
    common = _true(permission.get("allow_download")) and _true(permission.get("allow_cloudinary_storage")) and _true(permission.get("allow_new_caption"))
    if origin == "direct_reference" or content_type == "direct_reference_media" or mode in {"direct_reference_media", "saved_direct_reference_media"}:
        return "APPROVED" if common and _true(permission.get("allow_original_repost")) else "DENIED"
    clip_allowed = any(_true(permission.get(key)) for key in ("allow_clip_creation", "allow_derivative_clip", "allow_cut"))
    return "APPROVED" if common and clip_allowed else "DENIED"


def _is_direct_media_route(queue: Mapping[str, Any]) -> bool:
    return (
        _text(queue.get("media_origin")).lower() == "direct_reference"
        or _text(queue.get("content_type")).lower()
        == "direct_reference_media"
        or _text(queue.get("generation_mode")).lower()
        in {
            "direct_reference_media",
            "saved_direct_reference_media",
        }
    )


def _is_individual_source_url(platform: str, url: str) -> bool:
    value = _text(url).lower()
    platform = _text(platform).lower()
    if platform == "youtube":
        return bool(re.search(r"(?:watch\?v=|youtu\.be/|/shorts/)[a-z0-9_-]{6,}", value))
    if platform == "tiktok":
        return bool(re.search(r"/@[^/]+/video/\d+", value))
    if platform == "threads":
        return "/post/" in value
    if platform == "x":
        return bool(re.search(r"/status/\d+", value))
    if platform in {"owned_local", "system_owned"}:
        return True
    return False


def _ordered_parent_media(rows: list[dict[str, Any]], source_post_id: str) -> tuple[str, str]:
    if not source_post_id:
        return "NOT_REQUIRED", "NOT_REQUIRED"
    children = [row for row in rows if _text(row.get("source_post_id")) == source_post_id]
    if not children:
        return "BLOCKED", "BLOCKED"
    try:
        indexes = [int(str(row.get("media_index", "")).strip()) for row in children]
    except ValueError:
        return "PASS", "BLOCKED"
    return "PASS", "PASS" if sorted(indexes) == list(range(len(indexes))) else "BLOCKED"


def build_source_context(client: Any, queue: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    source_post_id = _text(queue.get("source_post_id"))
    source_video_id = _text(queue.get("source_video_id"))
    clip_candidate_id = _first(queue.get("clip_candidate_id"), queue.get("video_clip_id"))
    queue_source_id = _text(queue.get("source_id"))
    source_result_id = _text(queue.get("source_result_id"))

    source_post = _lookup(
        _read(client, "source_posts", errors, required=bool(source_post_id)),
        ("source_post_id", "post_id", "id"),
        source_post_id,
    ) if source_post_id else {}
    if source_post_id and not source_post and not errors:
        errors.append("source_posts:record_not_found")

    source_post_media = _read(
        client,
        "source_post_media",
        errors,
        required=bool(source_post_id),
    ) if source_post_id else []

    clip = _lookup(
        _read(client, "video_clip_candidates", errors, required=bool(clip_candidate_id)),
        ("clip_candidate_id", "clip_id", "id"),
        clip_candidate_id,
    ) if clip_candidate_id else {}
    if clip_candidate_id and not clip and not any(item.startswith("video_clip_candidates:") for item in errors):
        errors.append("video_clip_candidates:record_not_found")

    source_video = _lookup(
        _read(client, "source_videos", errors, required=bool(source_video_id)),
        ("source_video_id", "video_id", "id"),
        source_video_id,
    ) if source_video_id else {}
    if source_video_id and not source_video and not any(item.startswith("source_videos:") for item in errors):
        errors.append("source_videos:record_not_found")

    reference_post: dict[str, Any] = {}
    if queue_source_id and not source_post:
        for logical in ("source_account_posts", "reference_posts"):
            reference_post = _lookup(
                _read(client, logical, errors, required=False),
                ("source_id", "id", "post_id", "reference_post_id"),
                queue_source_id,
            )
            if reference_post:
                break

    posted_result = _lookup(
        _read(client, "posted_results", errors, required=False),
        ("result_id", "id"),
        source_result_id,
    ) if source_result_id else {}

    source_id = _first(
        queue_source_id, source_post.get("source_id"), reference_post.get("source_id"),
        clip.get("source_id"), source_video.get("source_id"), source_video.get("video_source_id"),
    )
    source: dict[str, Any] = {}
    if source_id:
        for logical in ("video_sources", "source_accounts", "reference_sources"):
            source = _lookup(_read(client, logical, errors, required=False), ("source_id", "id"), source_id)
            if source:
                break

    permission = _lookup(
        _read(client, "media_permissions", errors, required=False),
        ("source_id", "id"),
        source_id,
    ) if source_id else {}
    permission_status = _media_permission_status(queue, permission)

    canonical_source_url = _first(
        source_post.get("canonical_post_url"),
        source_post.get("individual_post_url"),
        source_video.get("canonical_video_url"),
        source_video.get("source_url"),
        clip.get("canonical_video_url"),
        queue.get("source_url"),
    )
    source_platform = _first(
        source_post.get("platform"), source_video.get("platform"),
        source.get("platform"), source.get("source_platform"), queue.get("source_platform"),
    ).lower()
    ownership = _first(queue.get("ownership"), queue.get("source_ownership")).lower()
    owned = ownership in {"owned", "system_owned"} or _text(queue.get("rights_status")).lower() == "owned"
    parent_identity_status = (
        "PASS" if owned or _is_individual_source_url(source_platform, canonical_source_url) else "BLOCKED"
    )
    author_identity_status = "PASS" if owned or bool(source_id and source) else "BLOCKED"
    media_parent_status, media_order_status = _ordered_parent_media(source_post_media, source_post_id)
    if not _is_direct_media_route(queue):
        media_parent_status = "NOT_REQUIRED"
        media_order_status = "NOT_REQUIRED"
    provenance_status = (
        "PASS"
        if permission_status in {"APPROVED", "NOT_REQUIRED"}
        and author_identity_status == "PASS"
        and parent_identity_status == "PASS"
        else "BLOCKED"
    )

    original_post_text = _first(
        source_post.get("original_post_text"), source_post.get("original_text"),
        source_post.get("text"), source_post.get("caption"), source_post.get("source_caption"),
        reference_post.get("original_post_text"), reference_post.get("original_text"),
        reference_post.get("post_text"), reference_post.get("text"),
        posted_result.get("posted_text"), posted_result.get("public_post_text"),
    )
    transcript_excerpt = _first(clip.get("transcript_excerpt"), clip.get("transcript_text"), clip.get("transcript"))
    direct_media_evidence = (
        _claim_support_evidence(queue.get("claim_support_json"))
        if _is_direct_media_route(queue)
        else ""
    )
    if direct_media_evidence:
        transcript_excerpt = "\n\n".join(
            dict.fromkeys(
                value
                for value in (
                    transcript_excerpt,
                    direct_media_evidence,
                )
                if value
            )
        )
    transcript = _first(source_video.get("transcript"), source_video.get("transcript_text"), source_video.get("full_transcript"))
    description = _first(source_video.get("description"), source_post.get("description"), reference_post.get("description"), source.get("description"))

    base_use_policy = _first(source.get("use_policy"), source_post.get("use_policy"), reference_post.get("use_policy"))
    effective_policy = "APPROVED_MEDIA_REUSE" if permission_status == "APPROVED" else base_use_policy
    # Canonical source-post text is the comparison source. Claim-support JSON is
    # private structured evidence and is only a fallback after safe extraction.
    source_text = _first(
        original_post_text,
        transcript_excerpt,
        transcript,
        description,
        _claim_support_evidence(queue.get("claim_support_json")),
    )

    return {
        "source_post_id": source_post_id,
        "source_video_id": source_video_id,
        "clip_candidate_id": clip_candidate_id,
        "source_id": source_id,
        "source_result_id": source_result_id,
        "original_post_text": original_post_text,
        "transcript_excerpt": transcript_excerpt,
        "transcript": transcript,
        "description": description,
        "source_text": source_text,
        "use_policy": effective_policy,
        "usage_scope": "APPROVED_MEDIA_REUSE" if permission_status == "APPROVED" else _first(source.get("usage_scope"), source_post.get("usage_scope"), reference_post.get("usage_scope")),
        "reuse_policy": "APPROVED" if permission_status == "APPROVED" else _first(source.get("reuse_policy"), source_post.get("reuse_policy"), reference_post.get("reuse_policy")),
        "source_target_account_id": _target_account(source, source_post, reference_post, source_video, clip, posted_result),
        "permission_evidence_status": permission_status,
        "canonical_source_url": canonical_source_url,
        "source_author_identity_status": author_identity_status,
        "source_parent_identity_status": parent_identity_status,
        "source_media_parent_status": media_parent_status,
        "source_media_order_status": media_order_status,
        "provenance_status": provenance_status,
        "clip_duration_seconds": _first(clip.get("duration_seconds"), clip.get("duration")),
        "clip_start_seconds": _first(clip.get("start_seconds"), clip.get("start_time")),
        "clip_end_seconds": _first(clip.get("end_seconds"), clip.get("end_time")),
        "classifier_model": os.environ.get("GEMINI_CLASSIFIER_MODEL", "gemini-3.1-flash-lite").strip(),
        "generator_model": os.environ.get("GEMINI_GENERATOR_MODEL", "gemini-3.5-flash").strip(),
        "review_model": os.environ.get("GEMINI_REVIEW_MODEL", "gemini-3.1-flash-lite").strip(),
        "read_errors": sorted(set(errors)),
    }


def hybrid_ai_source_context_hash(source_context: Mapping[str, Any]) -> str:
    payload: dict[str, Any] = {}
    for field in SOURCE_HASH_FIELDS:
        value = source_context.get(field)
        if field == "read_errors":
            payload[field] = sorted(str(item) for item in (value or []))
        else:
            payload[field] = _text(value)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
