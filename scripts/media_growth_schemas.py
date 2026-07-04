#!/usr/bin/env python3
"""Schemas and helper builders for Media Growth Engine dry-run outputs."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

VIDEO_TRANSCRIPT_FIELDS = [
    "transcript_id", "source_id", "source_url", "account_id", "platform",
    "video_id", "title", "transcript_status", "transcript_language",
    "transcript_text_redacted_preview", "transcript_hash", "chunk_count",
    "created_at", "rights_status", "permission_status",
]

VIDEO_CLIP_CANDIDATE_FIELDS = [
    "clip_candidate_id", "source_id", "account_id", "platform", "source_url",
    "video_id", "title", "start_seconds", "end_seconds", "duration_seconds",
    "transcript_excerpt", "hook_text", "reason", "expected_post_angle",
    "target_audience", "score", "rights_status", "permission_status",
    "cut_status", "upload_status", "post_status", "reviewer_status", "created_at",
    "hook_strength", "emotional_pull", "educational_value", "creator_relevance",
    "liver_manager_fit", "risk_score", "rights_score", "clip_score",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def redacted_preview(text: str, limit: int = 120) -> str:
    normalized = " ".join(str(text or "").split())
    return normalized[:limit]


def transcript_hash(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def build_transcript_row(source: dict[str, Any], *, status: str, title: str = "", text: str = "") -> dict[str, Any]:
    return {
        "transcript_id": f"tr_{source.get('source_id', 'unknown')}",
        "source_id": source.get("source_id", ""),
        "source_url": source.get("source_url", ""),
        "account_id": source.get("target_account_id", "liver_manager"),
        "platform": source.get("source_platform", ""),
        "video_id": "",
        "title": title,
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
