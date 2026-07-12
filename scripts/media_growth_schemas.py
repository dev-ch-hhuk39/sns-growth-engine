#!/usr/bin/env python3
"""Schemas and helper builders for Media Growth Engine dry-run outputs."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, urlsplit

VIDEO_TRANSCRIPT_FIELDS = [
    "transcript_id", "source_id", "source_url", "account_id", "platform",
    "video_id", "title", "transcript_status", "transcript_language",
    "transcript_text_redacted_preview", "transcript_hash", "chunk_count",
    "created_at", "rights_status", "permission_status",
]

VIDEO_CLIP_CANDIDATE_FIELDS = [
    "clip_candidate_id", "source_id", "account_id", "platform", "source_url",
    "source_video_id", "video_id", "canonical_video_url", "clip_index_in_video",
    "duplicate_clip_key", "overlap_group_id", "parent_video_duration_seconds",
    "transcript_signal_count", "can_create_multiple_clips", "selected_reason",
    "transcript_grounded", "transcript_id",
    "public_post_text", "public_post_validator_status",
    "title", "start_seconds", "end_seconds", "duration_seconds",
    "transcript_excerpt", "hook_text", "reason", "expected_post_angle",
    "target_audience", "score", "rights_status", "permission_status",
    "cut_status", "upload_status", "post_status", "reviewer_status", "created_at",
    "hook_strength", "emotional_pull", "educational_value", "creator_relevance",
    "liver_manager_fit", "risk_score", "rights_score", "clip_score",
]

SOURCE_VIDEO_FIELDS = [
    "source_video_id", "source_id", "account_id", "platform", "source_type",
    "source_url", "video_id", "canonical_video_url", "original_video_url",
    "title", "description_preview", "author_handle", "published_at",
    "duration_seconds", "view_count", "like_count", "comment_count",
    "transcript_status", "analysis_status", "clip_candidate_count",
    "download_status", "cut_status", "upload_status", "post_status",
    "rights_status", "permission_status", "discovery_status",
    "discovered_at", "last_seen_at", "processed_at", "skip_reason",
    "content_hash", "duplicate_key",
]

SOURCE_VIDEO_STATUS_FLOW = [
    "DISCOVERED", "TRANSCRIPT_PLANNED", "ANALYZED", "CLIP_CANDIDATES_READY",
    "DOWNLOADED", "CUT", "UPLOADED", "POSTED", "SKIPPED", "BLOCKED",
]

APPROVED_MEDIA_RIGHTS = {"owned", "licensed", "approved_creator_clip"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def redacted_preview(text: str, limit: int = 120) -> str:
    normalized = " ".join(str(text or "").split())
    return normalized[:limit]


def transcript_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def stable_hash(value: str, limit: int = 16) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:limit]


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]+", "_", str(value or "")).strip("_")[:80] or "unknown"


def extract_video_id(url: str, platform: str = "") -> str:
    parts = urlsplit(str(url or ""))
    host = parts.netloc.lower()
    path = parts.path.strip("/")
    qs = parse_qs(parts.query)
    if "youtube.com" in host and qs.get("v"):
        return qs["v"][0]
    if "youtu.be" in host and path:
        return path.split("/")[0]
    if "tiktok.com" in host and "/video/" in f"/{path}":
        return path.rsplit("/video/", 1)[-1].split("/")[0]
    return ""


def canonicalize_video_url(url: str, platform: str = "") -> str:
    parts = urlsplit(str(url or ""))
    host = parts.netloc.lower()
    video_id = extract_video_id(url, platform)
    if video_id and ("youtube.com" in host or "youtu.be" in host):
        return f"https://www.youtube.com/watch?v={video_id}"
    if video_id and "tiktok.com" in host:
        base_path = parts.path.split("/video/", 1)[0].rstrip("/")
        return f"https://www.tiktok.com{base_path}/video/{video_id}"
    return f"{parts.scheme or 'https'}://{parts.netloc}{parts.path}".rstrip("/")


def source_video_duplicate_key(row: dict[str, Any]) -> str:
    platform = str(row.get("platform", "") or row.get("source_platform", ""))
    source_id = str(row.get("source_id", ""))
    video_id = str(row.get("video_id", ""))
    canonical = str(row.get("canonical_video_url", ""))
    if video_id:
        return f"{platform}:{source_id}:video_id:{video_id}"
    if canonical:
        return f"{platform}:{source_id}:url:{canonicalize_video_url(canonical, platform)}"
    fallback = str(row.get("content_hash", "")) or stable_hash(
        f"{row.get('title','')}:{row.get('duration_seconds','')}:{row.get('description_preview','')}"
    )
    return f"{platform}:{source_id}:hash:{fallback}"


def is_duplicate_source_video(candidate: dict[str, Any], existing_rows: list[dict[str, Any]]) -> bool:
    candidate_key = source_video_duplicate_key(candidate)
    candidate_url = canonicalize_video_url(str(candidate.get("canonical_video_url", "")), str(candidate.get("platform", "")))
    for row in existing_rows:
        if source_video_duplicate_key(row) == candidate_key:
            return True
        if candidate_url and canonicalize_video_url(str(row.get("canonical_video_url", "")), str(row.get("platform", ""))) == candidate_url:
            return True
    return False


def build_source_video(
    source: dict[str, Any],
    index: int = 1,
    *,
    video_url: str = "",
    title: str = "",
    duration_seconds: int | float | None = None,
    description: str = "",
    discovery_status: str = "DISCOVERED",
) -> dict[str, Any]:
    platform = str(source.get("source_platform", ""))
    source_id = str(source.get("source_id", ""))
    source_url = str(source.get("source_url", ""))
    if not video_url:
        token = stable_hash(f"{source_id}:{index}", 12)
        if platform == "youtube":
            video_url = f"https://www.youtube.com/watch?v={token}"
        elif platform == "tiktok":
            video_url = f"{source_url.rstrip('/')}/video/{int(stable_hash(f'{source_id}:{index}', 8), 16) % 9000000000000000000 + 1000000000000000000}"
        else:
            video_url = source_url
    canonical = canonicalize_video_url(video_url, platform)
    video_id = extract_video_id(canonical, platform) or stable_hash(canonical, 12)
    duration = int(duration_seconds if duration_seconds is not None else (18 if index == 1 else 65 if index == 2 else 140))
    content = f"{source_id}:{canonical}:{title}:{duration}:{description}"
    row = {
        "source_video_id": f"sv_{_safe_id(source_id)}_{_safe_id(video_id)}",
        "source_id": source_id,
        "account_id": source.get("target_account_id") or (source.get("target_account_ids") or [""])[0],
        "platform": platform,
        "source_type": source.get("source_type", ""),
        "source_url": source_url,
        "video_id": video_id,
        "canonical_video_url": canonical,
        "original_video_url": video_url,
        "title": title or f"{source.get('source_name', source_id)} video candidate {index:02d}",
        "description_preview": redacted_preview(description or "candidate metadata only"),
        "author_handle": source.get("handle", ""),
        "published_at": "",
        "duration_seconds": duration,
        "view_count": "",
        "like_count": "",
        "comment_count": "",
        "transcript_status": "TRANSCRIPT_PLANNED",
        "analysis_status": "PENDING",
        "clip_candidate_count": 0,
        "download_status": "NOT_DOWNLOADED",
        "cut_status": "NOT_CUT",
        "upload_status": "NOT_UPLOADED",
        "post_status": "NOT_POSTED",
        "rights_status": source.get("rights_status", ""),
        "permission_status": source.get("permission_status", ""),
        "discovery_status": discovery_status,
        "discovered_at": now_iso(),
        "last_seen_at": now_iso(),
        "processed_at": "",
        "skip_reason": "",
        "content_hash": stable_hash(content, 24),
        "duplicate_key": "",
    }
    row["duplicate_key"] = source_video_duplicate_key(row)
    return row


def build_transcript_row(source: dict[str, Any], *, status: str, title: str = "", text: str = "", source_video: dict[str, Any] | None = None) -> dict[str, Any]:
    source_video = source_video or {}
    return {
        "transcript_id": f"tr_{source_video.get('source_video_id') or source.get('source_id', 'unknown')}",
        "source_id": source.get("source_id", ""),
        "source_url": source_video.get("canonical_video_url") or source.get("source_url", ""),
        "account_id": source.get("target_account_id", "liver_manager"),
        "platform": source.get("source_platform", ""),
        "video_id": source_video.get("video_id", ""),
        "title": title or source_video.get("title", ""),
        "transcript_status": status,
        "transcript_language": "ja",
        "transcript_text_redacted_preview": redacted_preview(text),
        "transcript_hash": transcript_hash(text) if text else "",
        "chunk_count": 0 if not text else max(1, len(text) // 500 + 1),
        "created_at": now_iso(),
        "rights_status": source.get("rights_status", ""),
        "permission_status": source.get("permission_status", ""),
    }


def score_clip_candidate(source: dict[str, Any], *, has_transcript: bool = False) -> dict[str, int]:
    rights_score = 20 if source.get("rights_status") in {"owned", "licensed", "approved_creator_clip"} else 0
    base = {
        "hook_strength": 14,
        "emotional_pull": 12,
        "educational_value": 14 if has_transcript else 10,
        "creator_relevance": 14,
        "liver_manager_fit": 18,
        "risk_score": 4,
        "rights_score": rights_score,
    }
    base["clip_score"] = min(100, base["hook_strength"] + base["emotional_pull"] + base["educational_value"] + base["creator_relevance"] + base["liver_manager_fit"] + base["rights_score"] - base["risk_score"])
    return base


def clip_count_for_video(video: dict[str, Any], config: dict[str, Any] | None = None, *, transcript_signal_count: int = 0) -> int:
    config = config or {}
    min_count = int(config.get("min_clip_candidates_per_video", 1))
    max_count = int(config.get("max_clip_candidates_per_video", 3))
    duration = float(video.get("duration_seconds") or 0)
    if duration < 25:
        count = 1
    elif duration <= 90:
        count = 2
    else:
        count = 3
    if transcript_signal_count and transcript_signal_count < count:
        count = max(1, transcript_signal_count)
    return max(min_count, min(max_count, count))


def duplicate_clip_key(clip: dict[str, Any]) -> str:
    return (
        f"{clip.get('platform','')}:{clip.get('video_id','')}:"
        f"{int(float(clip.get('start_seconds') or 0))}:"
        f"{int(float(clip.get('end_seconds') or 0))}"
    )


def clips_overlap(a: dict[str, Any], b: dict[str, Any], tolerance_seconds: int | float = 2) -> bool:
    if str(a.get("video_id", "")) != str(b.get("video_id", "")):
        return False
    a_start = float(a.get("start_seconds") or 0)
    a_end = float(a.get("end_seconds") or 0)
    b_start = float(b.get("start_seconds") or 0)
    b_end = float(b.get("end_seconds") or 0)
    return max(a_start, b_start) < min(a_end, b_end) + float(tolerance_seconds)


def build_clip_candidate_for_video(
    source: dict[str, Any],
    source_video: dict[str, Any],
    index: int = 1,
    *,
    config: dict[str, Any] | None = None,
    public_post_text: str = "",
    validator_status: str = "PASS",
    transcript_signal_count: int = 0,
    transcript_grounded: bool = False,
    transcript_id: str = "",
    transcript_excerpt: str = "",
    start_seconds: float | None = None,
    end_seconds: float | None = None,
) -> dict[str, Any]:
    config = config or {}
    duration = float(source_video.get("duration_seconds") or 60)
    clip_duration_max = float(config.get("clip_duration_max_seconds", 45))
    clip_duration_min = float(config.get("clip_duration_min_seconds", 8))
    planned_duration = max(clip_duration_min, min(clip_duration_max, duration if duration < 25 else 25))
    if start_seconds is not None and end_seconds is not None:
        start = max(0.0, float(start_seconds))
        end = min(duration, float(end_seconds)) if duration else float(end_seconds)
    elif duration < 25:
        start = 0
        end = min(duration, start + planned_duration)
    else:
        start = 10 + (index - 1) * int(planned_duration + 5)
        end = min(duration, start + planned_duration)
    if end <= start:
        start = 0
        end = min(duration, planned_duration)
    scores = score_clip_candidate(source, has_transcript=bool(transcript_signal_count))
    row = {
        "clip_candidate_id": f"clipcand_{source_video.get('source_video_id', source.get('source_id', 'unknown'))}_{index:02d}",
        "clip_id": f"clipcand_{source_video.get('source_video_id', source.get('source_id', 'unknown'))}_{index:02d}",
        "source_video_id": source_video.get("source_video_id", ""),
        "source_id": source.get("source_id", ""),
        "account_id": source_video.get("account_id") or source.get("target_account_id", "liver_manager"),
        "platform": source_video.get("platform") or source.get("source_platform", ""),
        "source_url": source_video.get("source_url") or source.get("source_url", ""),
        "source_video_url": source_video.get("canonical_video_url", ""),
        "video_id": source_video.get("video_id", ""),
        "canonical_video_url": source_video.get("canonical_video_url", ""),
        "clip_index_in_video": index,
        "overlap_group_id": f"og_{source_video.get('source_video_id', '')}_{index:02d}",
        "parent_video_duration_seconds": source_video.get("duration_seconds", ""),
        "transcript_signal_count": transcript_signal_count,
        "transcript_grounded": transcript_grounded,
        "transcript_id": transcript_id,
        "can_create_multiple_clips": clip_count_for_video(source_video, config, transcript_signal_count=transcript_signal_count) > 1,
        "selected_reason": "duration_and_hook_signal",
        "public_post_text": public_post_text,
        "public_post_validator_status": validator_status,
        "title": source_video.get("title", ""),
        "start_seconds": start,
        "end_seconds": end,
        "start_time": start,
        "end_time": end,
        "duration_seconds": round(end - start, 3),
        "transcript_excerpt": redacted_preview(transcript_excerpt, 120) if transcript_grounded else "redacted_plan_only",
        "hook_text": redacted_preview(transcript_excerpt, 60) if transcript_grounded else "配信で初見が入りやすくなる一言を切り出す",
        "reason": "video-level candidate with approved media rights",
        "expected_post_angle": "配信初心者が入りやすい空気を作る方法",
        "target_audience": "配信初心者 / ライバー候補",
        "score": scores["clip_score"],
        "rights_status": source_video.get("rights_status") or source.get("rights_status", ""),
        "permission_status": source_video.get("permission_status") or source.get("permission_status", ""),
        "cut_status": "NOT_CUT",
        "upload_status": "NOT_UPLOADED",
        "post_status": "NOT_POSTED",
        "reviewer_status": "WAITING_REVIEW",
        "clip_status": "WAITING_REVIEW",
        "created_at": now_iso(),
        **scores,
    }
    row["duplicate_clip_key"] = duplicate_clip_key(row)
    return row


def build_clip_candidate(source: dict[str, Any], index: int = 1, *, has_transcript: bool = False) -> dict[str, Any]:
    start = 10 + (index - 1) * 20
    end = start + 25
    scores = score_clip_candidate(source, has_transcript=has_transcript)
    row = {
        "clip_candidate_id": f"clipcand_{source.get('source_id', 'unknown')}_{index:02d}",
        "source_id": source.get("source_id", ""),
        "account_id": source.get("target_account_id", "liver_manager"),
        "platform": source.get("source_platform", ""),
        "source_url": source.get("source_url", ""),
        "video_id": "",
        "title": source.get("source_name", ""),
        "start_seconds": start,
        "end_seconds": end,
        "duration_seconds": end - start,
        "transcript_excerpt": "redacted_plan_only",
        "hook_text": "配信で初見が入りやすくなる一言を切り出す",
        "reason": "liver_manager audience fit and approved media rights",
        "expected_post_angle": "配信初心者が入りやすい空気を作る方法",
        "target_audience": "配信初心者 / ライバー候補",
        "score": scores["clip_score"],
        "rights_status": source.get("rights_status", ""),
        "permission_status": source.get("permission_status", ""),
        "cut_status": "NOT_CUT",
        "upload_status": "NOT_UPLOADED",
        "post_status": "NOT_POSTED",
        "reviewer_status": "WAITING_REVIEW",
        "created_at": now_iso(),
        **scores,
    }
    return row


def build_media_post_queue_item(clip: dict[str, Any], media_asset_id: str = "") -> dict[str, Any]:
    return {
        "queue_id": f"media_q_{clip.get('clip_candidate_id', 'unknown')}",
        "account_id": clip.get("account_id", "liver_manager"),
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "media_required": "true",
        "source_video_id": clip.get("source_video_id", ""),
        "clip_candidate_id": clip.get("clip_candidate_id", ""),
        "media_asset_id": media_asset_id,
        "public_post_text": clip.get("public_post_text", ""),
        "text": clip.get("public_post_text", ""),
        "validator_status": clip.get("public_post_validator_status", ""),
        "created_at": now_iso(),
    }


def build_media_pdca_records(clip: dict[str, Any], media_asset_id: str = "") -> dict[str, Any]:
    created = now_iso()
    return {
        "media_post_results": {
            "clip_candidate_id": clip.get("clip_candidate_id", ""),
            "media_asset_id": media_asset_id,
            "post_url": "",
            "posted_text": "",
            "account_id": clip.get("account_id", ""),
            "platform": "threads",
            "created_at": created,
        },
        "media_metrics": {
            "clip_candidate_id": clip.get("clip_candidate_id", ""),
            "views": "",
            "likes": "",
            "comments": "",
            "saves": "",
            "shares": "",
            "follows": "",
            "profile_clicks": "",
            "line_adds": "",
            "retention_proxy": "",
        },
        "clip_performance": {
            "clip_candidate_id": clip.get("clip_candidate_id", ""),
            "hook_type": clip.get("hook_text", ""),
            "clip_duration": clip.get("duration_seconds", ""),
            "subtitle_style": "burn_in_optional",
            "created_at": created,
        },
        "prompt_improvement_suggestions": {
            "suggestion_id": f"sug_{clip.get('clip_candidate_id', '')}",
            "clip_candidate_id": clip.get("clip_candidate_id", ""),
            "account_id": clip.get("account_id", ""),
            "status": "WAITING_REVIEW",
            "auto_apply": "false",
            "reason": "Media PDCA suggestions require human review.",
        },
        "learning_rules": {
            "active": "false",
            "auto_apply": "false",
        },
    }
