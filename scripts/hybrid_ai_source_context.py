#!/usr/bin/env python3
"""Resolve and hash the source evidence used by the hybrid AI gate."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Mapping

from sheets_record_reader import read_records_safely

TARGET_ACCOUNTS = {"night_scout", "liver_manager"}
SOURCE_HASH_FIELDS = (
    "source_post_id",
    "source_video_id",
    "clip_candidate_id",
    "source_id",
    "original_post_text",
    "transcript_excerpt",
    "transcript",
    "description",
    "source_text",
    "use_policy",
    "usage_scope",
    "reuse_policy",
    "source_target_account_id",
    "read_errors",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _read(client: Any, logical: str, errors: list[str]) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in read_records_safely(client, logical)]
    except Exception as exc:
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
        explicit = _first(
            row.get("target_account_id"),
            row.get("destination_account_id"),
            row.get("target_account"),
        )
        if explicit:
            return explicit
        account_id = _text(row.get("account_id"))
        if account_id in TARGET_ACCOUNTS:
            return account_id
    return ""


def build_source_context(client: Any, queue: Mapping[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    source_post_id = _text(queue.get("source_post_id"))
    source_video_id = _text(queue.get("source_video_id"))
    clip_candidate_id = _first(queue.get("clip_candidate_id"), queue.get("video_clip_id"))
    queue_source_id = _text(queue.get("source_id"))

    source_post: dict[str, Any] = {}
    if source_post_id:
        source_post = _lookup(
            _read(client, "source_posts", errors),
            ("source_post_id", "post_id", "id"),
            source_post_id,
        )

    clip: dict[str, Any] = {}
    if clip_candidate_id:
        clip = _lookup(
            _read(client, "video_clip_candidates", errors),
            ("clip_candidate_id", "clip_id", "id"),
            clip_candidate_id,
        )

    source_video: dict[str, Any] = {}
    if source_video_id:
        source_video = _lookup(
            _read(client, "source_videos", errors),
            ("source_video_id", "video_id", "id"),
            source_video_id,
        )

    source_id = _first(
        queue_source_id,
        source_post.get("source_id"),
        clip.get("source_id"),
        source_video.get("source_id"),
        source_video.get("video_source_id"),
    )

    source: dict[str, Any] = {}
    if source_id:
        for logical in ("video_sources", "source_accounts", "reference_sources"):
            rows = _read(client, logical, errors)
            source = _lookup(rows, ("source_id", "id"), source_id)
            if source:
                break

    original_post_text = _first(
        source_post.get("original_post_text"),
        source_post.get("original_text"),
        source_post.get("text"),
        source_post.get("caption"),
        source_post.get("source_caption"),
    )
    transcript_excerpt = _first(
        clip.get("transcript_excerpt"),
        clip.get("transcript_text"),
        clip.get("transcript"),
    )
    transcript = _first(
        source_video.get("transcript"),
        source_video.get("transcript_text"),
        source_video.get("full_transcript"),
    )
    description = _first(
        source_video.get("description"),
        source_post.get("description"),
        source.get("description"),
    )

    return {
        "source_post_id": source_post_id,
        "source_video_id": source_video_id,
        "clip_candidate_id": clip_candidate_id,
        "source_id": source_id,
        "original_post_text": original_post_text,
        "transcript_excerpt": transcript_excerpt,
        "transcript": transcript,
        "description": description,
        "source_text": _first(queue.get("claim_support_json")),
        "use_policy": _first(source.get("use_policy"), source_post.get("use_policy")),
        "usage_scope": _first(source.get("usage_scope"), source_post.get("usage_scope")),
        "reuse_policy": _first(source.get("reuse_policy"), source_post.get("reuse_policy")),
        "source_target_account_id": _target_account(source, source_post, source_video, clip),
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
