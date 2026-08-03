#!/usr/bin/env python3
"""Build review-only media activation evidence without Production mutation.

The builder reads exact approved direct-parent or exact approved-clip packets,
generates source-grounded public captions, evaluates semantic/public/media,
batch/topic and visual-plan evidence, then creates only WAITING_REVIEW rows.
It never writes Sheets, changes permission, prepares media, promotes READY,
dispatches workflows, or publishes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

ACCOUNTS = ("night_scout", "liver_manager")
ROUTES = ("direct_reference_media", "approved_source_clip")
APPROVED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}
QUALITY_GATE_VERSION = "generation_quality_v3"
FEATURE_SCHEMA_VERSION = "post_features_v1"
VISUAL_PLAN_VERSION = "visual_plan_v1"
GENERATION_RULE_VERSION = "media_activation_review_evidence_v2"
DANGEROUS_ENV = (
    "PUBLISH_ENABLED",
    "ALLOW_REAL_X_POST",
    "ALLOW_REAL_THREADS_POST",
    "ALLOW_MEDIA_POSTS",
    "ALLOW_REAL_THREADS_VIDEO_POST",
    "ALLOW_VIDEO_DOWNLOAD",
    "ALLOW_VIDEO_CUT",
    "ALLOW_CLOUDINARY_UPLOAD",
    "ALLOW_TRANSCRIPTION_API",
    "GITHUB_MODELS_ENABLED",
    "ENABLE_SENTENCE_TRANSFORMERS",
)

CaptionBuilder = Callable[[dict[str, Any], list[str]], dict[str, Any]]
QualityEvaluator = Callable[..., dict[str, Any]]
PublicValidator = Callable[[Any, str], dict[str, Any]]
MediaValidator = Callable[[dict[str, Any]], dict[str, Any]]
CandidateValidator = Callable[[dict[str, Any]], list[str]]
ActivationPlanner = Callable[[list[dict[str, Any]]], dict[str, Any]]
TopicValidator = Callable[..., dict[str, Any]]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _true(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "pass"}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sha_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safety_blockers(environ: Mapping[str, str] | None = None) -> list[str]:
    source = os.environ if environ is None else environ
    return [f"{name}=true" for name in DANGEROUS_ENV if _true(source.get(name))]


def _permission_id(row: Mapping[str, Any]) -> str:
    return _text(row.get("permission_id") or row.get("media_permission_id"))


def _media_id(row: Mapping[str, Any]) -> str:
    return _text(
        row.get("media_asset_id")
        or row.get("media_id")
        or row.get("source_post_media_id")
    )


def _media_url(row: Mapping[str, Any]) -> str:
    return _text(row.get("storage_url") or row.get("cloudinary_url"))


def _media_bundle(primary: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = primary.get("carousel_media")
    if isinstance(raw, list) and raw:
        return [dict(item) for item in raw if isinstance(item, dict)]
    return [dict(primary)]


def _publisher_media_type(media_types: Sequence[str]) -> str:
    normalized = [_text(value).lower() for value in media_types if _text(value)]
    if len(normalized) > 1:
        return "CAROUSEL"
    if normalized and normalized[0] == "image":
        return "IMAGE"
    return "VIDEO"


def _direct_runtime_content_type(media_types: Sequence[str]) -> str:
    normalized = [_text(value).lower() for value in media_types if _text(value)]
    if len(normalized) > 1:
        return "direct_carousel"
    if normalized and normalized[0] == "image":
        return "direct_image"
    return "direct_video"


ACCOUNT_EVIDENCE_TERMS: dict[str, tuple[str, ...]] = {
    "night_scout": (
        "夜職", "キャバ", "キャバ嬢", "ラウンジ", "風俗", "風俗嬢",
        "店", "店舗", "時給", "控除", "ノルマ", "罰金", "バック",
        "客層", "体験入店", "出勤", "移籍", "指名", "売上", "担当",
        "相談", "副業", "睡眠", "働く", "手取り",
    ),
    "liver_manager": (
        "配信", "配信者", "ライバー", "TikTok LIVE", "tiktoklive",
        "初見", "入室", "コメント", "リスナー", "ギフト", "投げ銭",
        "バトル", "事務所", "所属", "継続", "配信時間", "話題",
        "振り返り", "ダイヤ", "常連", "応援", "企画",
    ),
}
MIN_SOURCE_EVIDENCE_TERM_COUNT = 2
MIN_CLIP_TRANSCRIPT_CHARS = 30


def _compact_japanese(value: Any) -> str:
    return "".join(str(value or "").split()).casefold()


def _account_evidence_hits(account_id: str, value: Any) -> list[str]:
    compact = _compact_japanese(value)
    return sorted(
        {
            term
            for term in ACCOUNT_EVIDENCE_TERMS.get(account_id, ())
            if term.casefold() in compact
        }
    )


def _direct_source_suitability(
    *,
    account_id: str,
    post: Mapping[str, Any],
    media_evidence_text: str,
) -> tuple[dict[str, Any], list[str]]:
    original = _text(post.get("original_post_text"))
    cleaned = re.sub(r"https?://\S+", "", original)
    cleaned = re.sub(r"(?<!\S)[@#]\S+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    compact_source = re.sub(r"[\s\W_]+", "", cleaned, flags=re.UNICODE)
    source_usable = (
        len(compact_source) >= 20
        and bool(re.search(r"[ぁ-んァ-ヶ一-龠々]", cleaned))
    )
    source_hits = _account_evidence_hits(account_id, cleaned)
    media_hits = _account_evidence_hits(account_id, media_evidence_text)
    shared_hits = sorted(set(source_hits) & set(media_hits))
    blockers: list[str] = []
    if not source_usable:
        blockers.append("direct_source_post_text_unusable")
    if len(source_hits) < MIN_SOURCE_EVIDENCE_TERM_COUNT:
        blockers.append("direct_source_account_evidence_insufficient")
    if len(media_hits) < MIN_SOURCE_EVIDENCE_TERM_COUNT:
        blockers.append("direct_media_account_evidence_insufficient")
    if source_hits and media_hits and not shared_hits:
        blockers.append("direct_source_media_topic_mismatch")
    return {
        "source_text_hash": _sha_text(cleaned) if cleaned else "",
        "source_text_length": len(cleaned),
        "source_text_usable": source_usable,
        "source_account_terms": source_hits,
        "media_account_terms": media_hits,
        "shared_account_terms": shared_hits,
        "minimum_account_term_count": MIN_SOURCE_EVIDENCE_TERM_COUNT,
    }, sorted(set(blockers))


def _clip_source_suitability(
    *,
    account_id: str,
    transcript: str,
) -> tuple[dict[str, Any], list[str]]:
    compact = _compact_japanese(transcript)
    hits = _account_evidence_hits(account_id, transcript)
    blockers: list[str] = []
    if len(compact) < MIN_CLIP_TRANSCRIPT_CHARS:
        blockers.append("clip_transcript_too_short_for_grounding")
    if len(hits) < MIN_SOURCE_EVIDENCE_TERM_COUNT:
        blockers.append("clip_account_evidence_insufficient")
    return {
        "transcript_hash": _sha_text(transcript) if transcript else "",
        "transcript_compact_length": len(compact),
        "account_terms": hits,
        "minimum_account_term_count": MIN_SOURCE_EVIDENCE_TERM_COUNT,
        "minimum_transcript_chars": MIN_CLIP_TRANSCRIPT_CHARS,
    }, sorted(set(blockers))


def _source_evidence_blockers(values: Sequence[str]) -> list[str]:
    prefixes = (
        "direct_source_",
        "direct_media_",
        "clip_transcript_",
        "clip_account_",
    )
    return sorted(
        {
            _text(value)
            for value in values
            if _text(value).startswith(prefixes)
        }
    )


def _history_texts(
    account_id: str,
    queue_rows: Sequence[Mapping[str, Any]],
    posted_results: Sequence[Mapping[str, Any]],
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for rows, pending in ((posted_results, False), (queue_rows, True)):
        for row in rows:
            if _text(row.get("account_id") or row.get("target_account_id")) != account_id:
                continue
            if pending and _text(row.get("status")).upper() not in {
                "WAITING_REVIEW",
                "READY",
                "PROCESSING",
            }:
                continue
            if not pending and _text(row.get("status")).upper() not in {"POSTED", "COMPLETE"}:
                continue
            text = _text(row.get("posted_text") or row.get("public_post_text") or row.get("text"))
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
    return result[-40:]


def _direct_media_evidence(primary_media: Mapping[str, Any]) -> tuple[str, dict[str, Any], list[str]]:
    bundle = _media_bundle(primary_media)
    evidence_parts: list[str] = []
    item_summaries: list[dict[str, Any]] = []
    blockers: list[str] = []
    for item in bundle:
        understanding = item.get("media_understanding")
        if not isinstance(understanding, dict):
            understanding = {}
        status = _text(understanding.get("status")).upper()
        values = [
            _text(understanding.get("visual_summary")),
            _text(understanding.get("visible_text")),
            _text(understanding.get("ocr_text")),
            _text(understanding.get("transcript_text")),
        ]
        values = [value for value in values if value]
        media_id = _media_id(item)
        if status != "PASS":
            blockers.append(f"{media_id or 'media'}:media_understanding_not_pass")
        if not values:
            blockers.append(f"{media_id or 'media'}:media_understanding_empty")
        evidence_parts.extend(values)
        item_summaries.append(
            {
                "media_asset_id": media_id,
                "media_type": _text(item.get("media_type")).lower(),
                "understanding_status": status,
                "understanding_hash": _sha_text("\n".join(values)) if values else "",
            }
        )
    evidence = "\n".join(evidence_parts).strip()[:16000]
    if not evidence:
        blockers.append("direct_media_evidence_missing")
    return evidence, {"items": item_summaries, "item_count": len(bundle)}, sorted(set(blockers))


def _clip_media_evidence(
    clip: Mapping[str, Any],
    source_video: Mapping[str, Any],
    asset: Mapping[str, Any],
) -> tuple[str, dict[str, Any], list[str]]:
    transcript = _text(clip.get("transcript_excerpt") or clip.get("transcript_text"))
    start = _text(clip.get("start_seconds") or clip.get("start_time"))
    end = _text(clip.get("end_seconds") or clip.get("end_time"))
    blockers: list[str] = []
    if not _true(clip.get("transcript_grounded")):
        blockers.append("transcript_grounding_required")
    if not transcript:
        blockers.append("transcript_excerpt_missing")
    if not start or not end:
        blockers.append("exact_clip_time_range_missing")
    if not _text(source_video.get("canonical_video_url") or source_video.get("source_video_url")):
        blockers.append("source_video_url_missing")
    if not _media_id(asset) or not _media_url(asset):
        blockers.append("persisted_media_asset_missing")
    packet = {
        "clip_candidate_id": _text(clip.get("clip_candidate_id") or clip.get("clip_id")),
        "source_video_id": _text(source_video.get("source_video_id") or clip.get("source_video_id")),
        "media_asset_id": _media_id(asset),
        "start_seconds": start,
        "end_seconds": end,
        "transcript_hash": _sha_text(transcript) if transcript else "",
    }
    return transcript[:16000], packet, sorted(set(blockers))


def _validation_status(result: Mapping[str, Any], field: str) -> str:
    nested = result.get(field)
    if isinstance(nested, Mapping):
        status = _text(nested.get("status")).upper()
        if status:
            return status
    return "PASS" if _text(result.get("status")).upper() == "PASS" else "BLOCKED"


def _alignment_fields(caption: Mapping[str, Any]) -> dict[str, Any]:
    semantic = caption.get("semantic_alignment")
    if not isinstance(semantic, Mapping):
        semantic = {}
    return {
        "alignment_status": _text(
            caption.get("alignment_status") or semantic.get("status")
        ).upper(),
        "final_alignment_score": caption.get(
            "final_alignment_score", semantic.get("final_alignment_score", "")
        ),
        "main_claim_coverage": caption.get(
            "main_claim_coverage", semantic.get("main_claim_coverage", "")
        ),
        "unsupported_claim_count": caption.get(
            "unsupported_claim_count", semantic.get("unsupported_claim_count", "")
        ),
        "source_copy_similarity": caption.get(
            "source_copy_similarity", semantic.get("source_copy_similarity", "")
        ),
        "recent_post_similarity": caption.get(
            "recent_post_similarity", semantic.get("recent_post_similarity", "")
        ),
        "claim_support_json": (
            _text(caption.get("claim_support_json"))
            or _stable_json(caption.get("claim_support", []))
        ),
    }


def _draft_common_blockers(
    *,
    account_id: str,
    route: str,
    permission: Mapping[str, Any],
    media_id: str,
    media_url: str,
) -> list[str]:
    blockers: list[str] = []
    if account_id not in ACCOUNTS:
        blockers.append("unsupported_account")
    if route not in ROUTES:
        blockers.append("unsupported_route")
    if _text(permission.get("rights_status")).lower() not in APPROVED_RIGHTS:
        blockers.append("rights_status_not_approved")
    if _text(permission.get("permission_status")).lower() != "approved":
        blockers.append("permission_status_not_approved")
    if not _permission_id(permission):
        blockers.append("permission_id_missing")
    if not _text(permission.get("evidence_reference")):
        blockers.append("permission_evidence_missing")
    if not media_id:
        blockers.append("media_asset_id_missing")
    if not media_url:
        blockers.append("media_url_missing")
    return blockers


@dataclass
class EvidenceDraft:
    account_id: str
    route: str
    source: dict[str, Any]
    public_post_text: str
    caption: dict[str, Any]
    public_validation: dict[str, Any]
    media_validation: dict[str, Any]
    media_evidence_text: str
    media_evidence_summary: dict[str, Any]
    structure_variant: str
    blockers: list[str]


def build_direct_draft(
    *,
    account_id: str,
    selection: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
    permission: Mapping[str, Any],
    recent_posts: list[str],
    caption_builder: CaptionBuilder,
    public_validator: PublicValidator,
    media_validator: MediaValidator,
) -> EvidenceDraft:
    post, primary_media, source = (dict(item) for item in selection)
    bundle = _media_bundle(primary_media)
    media_ids = [_media_id(item) for item in bundle]
    media_urls = [_media_url(item) for item in bundle]
    media_types = [_text(item.get("media_type")).lower() for item in bundle]
    evidence_text, evidence_summary, blockers = _direct_media_evidence(primary_media)
    suitability, suitability_blockers = _direct_source_suitability(
        account_id=account_id,
        post=post,
        media_evidence_text=evidence_text,
    )
    evidence_summary["source_suitability"] = suitability
    blockers.extend(suitability_blockers)
    blockers.extend(
        _draft_common_blockers(
            account_id=account_id,
            route="direct_reference_media",
            permission=permission,
            media_id=media_ids[0] if media_ids else "",
            media_url=media_urls[0] if media_urls else "",
        )
    )
    packet = {
        "account_id": account_id,
        "route": "direct_reference_media",
        "post": post,
        "primary_media": primary_media,
        "source": source,
        "permission": dict(permission),
        "media_evidence_text": evidence_text,
    }
    pre_generation_blocked = bool(blockers)
    caption = caption_builder(packet, recent_posts) if not pre_generation_blocked else {}
    public_text = _text(caption.get("public_post_text"))
    if not pre_generation_blocked:
        if _text(caption.get("status")).upper() != "PASS" or not public_text:
            blockers.extend(
                _text(reason)
                for reason in caption.get("blocked_reasons", ["caption_generation_not_pass"])
                if _text(reason)
            )
            if not public_text:
                blockers.append("public_post_text_missing")
        public_validation = public_validator(public_text, account_id) if public_text else {"status": "BLOCKED"}
        if _text(public_validation.get("status")).upper() != "PASS":
            blockers.extend(
                _text(reason)
                for reason in public_validation.get("blocked_reasons", ["public_validator_not_pass"])
                if _text(reason)
            )
    else:
        public_validation = {"status": "BLOCKED", "blocked_reasons": []}
    alignment = _alignment_fields(caption)
    media_plan = {
        "rights_status": permission.get("rights_status", ""),
        "permission_status": permission.get("permission_status", ""),
        "media_url": media_urls[0] if media_urls else "",
        "media_urls": media_urls,
        "media_asset_id": media_ids[0] if media_ids else "",
        "platform": "threads",
        "account_id": account_id,
        "media_type": media_types[0] if media_types else "",
        "content_type": _direct_runtime_content_type(media_types),
        "publisher_media_type": _publisher_media_type(media_types),
        "duration_seconds": primary_media.get("duration_seconds", ""),
        "aspect_ratio": primary_media.get("aspect_ratio", ""),
        "public_post_text": public_text,
        "media_origin": "direct_reference",
        "caption_mode": "source_copyedit",
        **alignment,
    }
    media_validation = (
        media_validator(media_plan)
        if public_text and not pre_generation_blocked
        else {"status": "BLOCKED", "blocked_reasons": []}
    )
    if (
        not pre_generation_blocked
        and _text(media_validation.get("status")).upper() != "PASS"
    ):
        blockers.extend(
            _text(reason)
            for reason in media_validation.get("blocked_reasons", ["media_validator_not_pass"])
            if _text(reason)
        )
    return EvidenceDraft(
        account_id=account_id,
        route="direct_reference_media",
        source={
            "source_id": _text(post.get("source_id") or source.get("source_id")),
            "source_post_id": _text(post.get("source_post_id")),
            "source_url": _text(post.get("canonical_post_url") or post.get("post_url")),
            "permission_id": _permission_id(permission),
            "permission_evidence": _text(permission.get("evidence_reference")),
            "rights_status": _text(permission.get("rights_status")),
            "permission_status": _text(permission.get("permission_status")),
            "media_asset_id": media_ids[0] if media_ids else "",
            "media_url": media_urls[0] if media_urls else "",
            "media_asset_ids_json": _stable_json(media_ids),
            "media_urls_json": _stable_json(media_urls),
            "media_types_json": _stable_json(media_types),
            "media_type": media_types[0] if media_types else "",
            "publisher_media_type": _publisher_media_type(media_types),
            "media_origin": "direct_reference",
            "duration_seconds": primary_media.get("duration_seconds", ""),
            "aspect_ratio": primary_media.get("aspect_ratio", ""),
            "content_hash": _text(post.get("content_hash")),
        },
        public_post_text=public_text,
        caption=dict(caption),
        public_validation=dict(public_validation),
        media_validation=dict(media_validation),
        media_evidence_text=evidence_text,
        media_evidence_summary=evidence_summary,
        structure_variant="source_preserving_parent",
        blockers=sorted(set(blockers)),
    )


def build_clip_draft(
    *,
    account_id: str,
    selection: tuple[dict[str, Any], dict[str, Any], dict[str, Any]],
    permission: Mapping[str, Any],
    recent_posts: list[str],
    caption_builder: CaptionBuilder,
    public_validator: PublicValidator,
    media_validator: MediaValidator,
) -> EvidenceDraft:
    clip, source_video, asset = (dict(item) for item in selection)
    evidence_text, evidence_summary, blockers = _clip_media_evidence(clip, source_video, asset)
    suitability, suitability_blockers = _clip_source_suitability(
        account_id=account_id,
        transcript=evidence_text,
    )
    evidence_summary["source_suitability"] = suitability
    blockers.extend(suitability_blockers)
    media_id = _media_id(asset)
    media_url = _media_url(asset)
    blockers.extend(
        _draft_common_blockers(
            account_id=account_id,
            route="approved_source_clip",
            permission=permission,
            media_id=media_id,
            media_url=media_url,
        )
    )
    packet = {
        "account_id": account_id,
        "route": "approved_source_clip",
        "clip": clip,
        "source_video": source_video,
        "asset": asset,
        "permission": dict(permission),
        "media_evidence_text": evidence_text,
    }
    pre_generation_blocked = bool(blockers)
    caption = caption_builder(packet, recent_posts) if not pre_generation_blocked else {}
    public_text = _text(caption.get("public_post_text"))
    if not pre_generation_blocked:
        if _text(caption.get("status")).upper() != "PASS" or not public_text:
            blockers.extend(
                _text(reason)
                for reason in caption.get("blocked_reasons", ["caption_generation_not_pass"])
                if _text(reason)
            )
            if not public_text:
                blockers.append("public_post_text_missing")
        public_validation = public_validator(public_text, account_id) if public_text else {"status": "BLOCKED"}
        if _text(public_validation.get("status")).upper() != "PASS":
            blockers.extend(
                _text(reason)
                for reason in public_validation.get("blocked_reasons", ["public_validator_not_pass"])
                if _text(reason)
            )
    else:
        public_validation = {"status": "BLOCKED", "blocked_reasons": []}
    alignment = _alignment_fields(caption)
    media_plan = {
        "rights_status": permission.get("rights_status", ""),
        "permission_status": permission.get("permission_status", ""),
        "media_url": media_url,
        "media_asset_id": media_id,
        "platform": "threads",
        "account_id": account_id,
        "media_type": "video",
        "content_type": "approved_source_clip",
        "publisher_media_type": "VIDEO",
        "duration_seconds": asset.get("duration_seconds") or asset.get("duration", ""),
        "aspect_ratio": asset.get("aspect_ratio", ""),
        "public_post_text": public_text,
        "media_origin": "approved_source_clip",
        "caption_mode": "transform",
        "enforce_video_stream_evidence": "true",
        "video_stream_count": asset.get("video_stream_count", ""),
        "audio_stream_count": asset.get("audio_stream_count", ""),
        "media_probe_status": asset.get("media_probe_status", ""),
        **alignment,
    }
    media_validation = (
        media_validator(media_plan)
        if public_text and not pre_generation_blocked
        else {"status": "BLOCKED", "blocked_reasons": []}
    )
    if (
        not pre_generation_blocked
        and _text(media_validation.get("status")).upper() != "PASS"
    ):
        blockers.extend(
            _text(reason)
            for reason in media_validation.get("blocked_reasons", ["media_validator_not_pass"])
            if _text(reason)
        )
    return EvidenceDraft(
        account_id=account_id,
        route="approved_source_clip",
        source={
            "source_id": _text(source_video.get("source_id") or clip.get("source_id")),
            "source_video_id": _text(source_video.get("source_video_id") or clip.get("source_video_id")),
            "clip_candidate_id": _text(clip.get("clip_candidate_id") or clip.get("clip_id")),
            "source_video_url": _text(
                source_video.get("canonical_video_url") or source_video.get("source_video_url")
            ),
            "start_seconds": _text(clip.get("start_seconds") or clip.get("start_time")),
            "end_seconds": _text(clip.get("end_seconds") or clip.get("end_time")),
            "permission_id": _permission_id(permission),
            "permission_evidence": _text(permission.get("evidence_reference")),
            "rights_status": _text(permission.get("rights_status")),
            "permission_status": _text(permission.get("permission_status")),
            "media_asset_id": media_id,
            "media_url": media_url,
            "media_type": "video",
            "publisher_media_type": "VIDEO",
            "media_origin": "approved_source_clip",
            "duration_seconds": asset.get("duration_seconds") or asset.get("duration", ""),
            "aspect_ratio": asset.get("aspect_ratio", ""),
            "width": asset.get("width", ""),
            "height": asset.get("height", ""),
            "video_stream_count": asset.get("video_stream_count", ""),
            "audio_stream_count": asset.get("audio_stream_count", ""),
            "media_probe_status": asset.get("media_probe_status", ""),
            "enforce_video_stream_evidence": "true",
            "content_hash": _text(clip.get("content_hash") or source_video.get("content_hash")),
        },
        public_post_text=public_text,
        caption=dict(caption),
        public_validation=dict(public_validation),
        media_validation=dict(media_validation),
        media_evidence_text=evidence_text,
        media_evidence_summary=evidence_summary,
        structure_variant="exact_clip_grounded",
        blockers=sorted(set(blockers)),
    )


def build_visual_plan_v1(
    draft: EvidenceDraft,
    quality: Mapping[str, Any],
    *,
    topic_validator: TopicValidator,
) -> tuple[dict[str, Any], list[str]]:
    blockers: list[str] = []
    primary_topic = _text(quality.get("primary_topic"))
    if not primary_topic:
        blockers.append("visual_primary_topic_missing")
    if not draft.media_evidence_text:
        blockers.append("visual_media_evidence_missing")
    topic = topic_validator(
        draft.account_id,
        draft.public_post_text,
        visual_text=draft.media_evidence_text,
        primary_topic=primary_topic,
    )
    visual_topic = _text(topic.get("visual_topic"))
    visual_topic_match = _true(topic.get("visual_topic_match"))
    if not visual_topic:
        blockers.append("visual_topic_missing")
    if not visual_topic_match:
        blockers.append("visual_topic_mismatch")
    evidence_hash = _sha_text(draft.media_evidence_text)
    public_hash = _sha_text(draft.public_post_text)
    binding_payload = {
        "account_id": draft.account_id,
        "content_route": draft.route,
        "media_asset_id": draft.source.get("media_asset_id", ""),
        "media_evidence_hash": evidence_hash,
        "public_post_hash": public_hash,
        "primary_topic": primary_topic,
        "visual_topic": visual_topic,
        "overlay_mode": "none_existing_approved_media",
        "caption_cta_channel": "caption_only",
    }
    plan = {
        "visual_plan_version": VISUAL_PLAN_VERSION,
        "visual_mode": "existing_approved_media",
        "overlay_mode": "none_existing_approved_media",
        "caption_cta_channel": "caption_only",
        "visual_cta_policy_status": "PASS",
        "visual_cta_match": True,
        "media_primary_topic": primary_topic,
        "visual_topic": visual_topic,
        "visual_topic_match": visual_topic_match,
        "visual_text_hash": evidence_hash,
        "public_post_hash": public_hash,
        "content_binding_hash": _sha_text(_stable_json(binding_payload)),
        "media_evidence_summary": deepcopy(draft.media_evidence_summary),
    }
    return plan, sorted(set(blockers))


def finalize_draft(
    draft: EvidenceDraft,
    *,
    batch_id: str,
    history: list[str],
    sibling_drafts: Sequence[EvidenceDraft],
    quality_evaluator: QualityEvaluator,
    topic_validator: TopicValidator,
    candidate_validator: CandidateValidator,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    blockers = list(draft.blockers)
    source_blockers = _source_evidence_blockers(blockers)
    if source_blockers:
        diagnostic = {
            "account_id": draft.account_id,
            "content_route": draft.route,
            "status": "BLOCKED",
            "blockers": sorted(set(blockers)),
            "public_post_hash": "",
            "media_evidence_hash": (
                _sha_text(draft.media_evidence_text)
                if draft.media_evidence_text
                else ""
            ),
            "candidate_contract_blockers": [],
            "source_evidence_status": "SOURCE_EVIDENCE_UNSUITABLE",
            "source_evidence_summary": deepcopy(
                draft.media_evidence_summary.get("source_suitability", {})
            ),
        }
        return None, diagnostic
    siblings = [
        {
            "account_id": item.account_id,
            "content_route": item.route,
            "candidate_id": f"draft:{item.account_id}:{item.route}",
            "public_post_text": item.public_post_text,
            "structure_variant": item.structure_variant,
        }
        for item in sibling_drafts
        if item is not draft and item.public_post_text
    ]
    quality = quality_evaluator(
        draft.account_id,
        draft.public_post_text,
        list(history) + siblings,
        batch_compared=siblings,
        structure_variant=draft.structure_variant,
        visual_text=draft.media_evidence_text,
        primary_topic="",
    ) if draft.public_post_text else {"status": "BLOCKED"}
    if _text(quality.get("status")).upper() != "PASS":
        blockers.extend(
            _text(reason)
            for reason in quality.get("diversity_blocked_reasons", [])
            if _text(reason)
        )
        blockers.extend(
            _text(reason)
            for reason in quality.get("topic_blocked_reasons", [])
            if _text(reason)
        )
        blockers.append("generation_quality_not_pass")
    visual, visual_blockers = build_visual_plan_v1(
        draft,
        quality,
        topic_validator=topic_validator,
    )
    blockers.extend(visual_blockers)
    alignment = _alignment_fields(draft.caption)
    public_hash = _sha_text(draft.public_post_text) if draft.public_post_text else ""
    alignment_public_hash = _text(
        draft.caption.get("public_post_hash")
        or draft.caption.get("alignment_public_hash")
    )
    if alignment_public_hash and alignment_public_hash != public_hash:
        blockers.append("alignment_public_post_hash_mismatch")
    if _text(draft.public_validation.get("status")).upper() != "PASS":
        blockers.append("public_validation_not_pass")
    if _text(draft.media_validation.get("status")).upper() != "PASS":
        blockers.append("media_validation_not_pass")
    candidate = {
        **deepcopy(draft.source),
        "account_id": draft.account_id,
        "content_route": draft.route,
        "content_type": draft.route,
        "batch_id": batch_id,
        "canary_id": f"canary_fresh_media_activation_{batch_id}_{draft.account_id}_{draft.route}",
        "status": "WAITING_REVIEW",
        "auto_publish": "false",
        "ai_publish_recommendation": "review",
        "public_post_text": draft.public_post_text,
        "public_post_hash": public_hash,
        "validator_status": _text(draft.public_validation.get("status")).upper(),
        "internal_leak_status": _validation_status(draft.public_validation, "internal_leak_check"),
        "account_fit_status": _validation_status(draft.public_validation, "account_fit_check"),
        "caption_provider": _text(
            draft.caption.get("caption_provider") or draft.caption.get("provider_name")
        ),
        "caption_provider_version": _text(
            draft.caption.get("caption_provider_version") or draft.caption.get("provider_version")
        ),
        **alignment,
        "batch_diversity_status": _text(quality.get("batch_diversity_status")).upper(),
        "batch_similarity_score": quality.get("batch_similarity_score", ""),
        "primary_topic": quality.get("primary_topic", ""),
        "supporting_topics": _stable_json(quality.get("supporting_topics", [])),
        "topic_confidence": quality.get("topic_confidence", ""),
        "topic_coherence_status": _text(quality.get("topic_coherence_status")).upper(),
        "topic_coherence_score": quality.get("topic_coherence_score", ""),
        "structure_variant": draft.structure_variant,
        "hook_topic_match": quality.get("hook_topic_match", False),
        "closing_topic_match": quality.get("closing_topic_match", False),
        "quality_gate_version": _text(quality.get("quality_gate_version")) or QUALITY_GATE_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "generation_attempt": draft.caption.get("caption_attempt_count") or draft.caption.get("primary_attempt_count") or 1,
        "generation_rule_version": GENERATION_RULE_VERSION,
        "generation_policy_json": _stable_json(
            {
                "policy_version": GENERATION_RULE_VERSION,
                "mode": "exact_source_review_only",
                "content_route": draft.route,
                "production_write": False,
            }
        ),
        **visual,
        "visual_plan_json": _stable_json(visual),
        "created_at": _now(),
        "updated_at": _now(),
    }
    contract_blockers = candidate_validator(deepcopy(candidate))
    blockers.extend(contract_blockers)
    blockers = sorted(set(_text(item) for item in blockers if _text(item)))
    diagnostic = {
        "account_id": draft.account_id,
        "content_route": draft.route,
        "status": "PASS" if not blockers else "BLOCKED",
        "blockers": blockers,
        "public_post_hash": public_hash,
        "media_evidence_hash": visual.get("visual_text_hash", ""),
        "candidate_contract_blockers": contract_blockers,
        "source_evidence_status": (
            "SOURCE_EVIDENCE_UNSUITABLE"
            if _source_evidence_blockers(blockers)
            else "PASS"
        ),
        "source_evidence_summary": deepcopy(
            draft.media_evidence_summary.get("source_suitability", {})
        ),
    }
    return (candidate if not blockers else None), diagnostic


def build_review_evidence_plan(
    *,
    direct_selections: Mapping[
        str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None
    ],
    clip_selections: Mapping[
        str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None
    ],
    permissions: Mapping[tuple[str, str], Mapping[str, Any]],
    queue_rows: Sequence[Mapping[str, Any]],
    posted_results: Sequence[Mapping[str, Any]],
    batch_id: str,
    direct_caption_builder: CaptionBuilder,
    clip_caption_builder: CaptionBuilder,
    direct_public_validator: PublicValidator,
    clip_public_validator: PublicValidator,
    media_validator: MediaValidator,
    quality_evaluator: QualityEvaluator,
    topic_validator: TopicValidator,
    candidate_validator: CandidateValidator,
    activation_planner: ActivationPlanner,
) -> dict[str, Any]:
    drafts: list[EvidenceDraft] = []
    missing: list[str] = []
    for account_id in ACCOUNTS:
        history = _history_texts(account_id, queue_rows, posted_results)
        direct = direct_selections.get(account_id)
        direct_permission = permissions.get((account_id, "direct_reference_media"), {})
        if direct is None:
            missing.append(f"{account_id}:direct_reference_media")
        else:
            drafts.append(
                build_direct_draft(
                    account_id=account_id,
                    selection=direct,
                    permission=direct_permission,
                    recent_posts=history,
                    caption_builder=direct_caption_builder,
                    public_validator=direct_public_validator,
                    media_validator=media_validator,
                )
            )
        clip = clip_selections.get(account_id)
        clip_permission = permissions.get((account_id, "approved_source_clip"), {})
        if clip is None:
            missing.append(f"{account_id}:approved_source_clip")
        else:
            drafts.append(
                build_clip_draft(
                    account_id=account_id,
                    selection=clip,
                    permission=clip_permission,
                    recent_posts=history,
                    caption_builder=clip_caption_builder,
                    public_validator=clip_public_validator,
                    media_validator=media_validator,
                )
            )
    rows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for draft in drafts:
        history = _history_texts(draft.account_id, queue_rows, posted_results)
        candidate, diagnostic = finalize_draft(
            draft,
            batch_id=batch_id,
            history=history,
            sibling_drafts=[item for item in drafts if item.account_id == draft.account_id],
            quality_evaluator=quality_evaluator,
            topic_validator=topic_validator,
            candidate_validator=candidate_validator,
        )
        diagnostics.append(diagnostic)
        if candidate is not None:
            rows.append(candidate)
    activation = activation_planner(deepcopy(rows))
    status = "PASS" if len(rows) == 4 and not missing and _text(activation.get("status")) == "PASS" else "BLOCKED"
    return {
        "status": status,
        "read_status": "READ_ONLY_COMPLETE",
        "batch_id": batch_id,
        "expected_candidate_count": 4,
        "candidate_count": len(rows),
        "missing_source_slots": sorted(missing),
        "candidate_diagnostics": diagnostics,
        "candidates": rows,
        "activation_plan": activation,
        "safety": {
            "production_write": False,
            "sheets_write": False,
            "permission_mutation": False,
            "caption_generation": True,
            "external_model_call": False,
            "media_download": False,
            "media_cut": False,
            "media_upload": False,
            "queue_write": False,
            "ready_transition": False,
            "workflow_dispatch": False,
            "sns_post": False,
        },
    }


def _active_permission_row(
    rows: Sequence[Mapping[str, Any]],
    *,
    account_id: str,
    source_id: str,
    operation: str,
    checker: Callable[..., bool],
) -> dict[str, Any]:
    candidates = [
        dict(row)
        for row in rows
        if _text(row.get("source_id")) == source_id
        and checker(row, account_id=account_id, operation=operation)
    ]
    candidates.sort(
        key=lambda row: (
            _text(row.get("updated_at") or row.get("created_at")),
            _permission_id(row),
        ),
        reverse=True,
    )
    return candidates[0] if candidates else {}


def select_source_suitable_direct_candidate(
    candidates: Sequence[
        tuple[
            dict[str, Any],
            dict[str, Any],
            dict[str, Any],
        ]
    ],
    *,
    permissions: Sequence[Mapping[str, Any]],
    account_id: str,
    permission_checker: Callable[..., bool],
) -> tuple[
    tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ]
    | None,
    dict[str, Any],
    list[dict[str, Any]],
]:
    # Select the first permissioned candidate whose source and media agree.
    #
    # Selection order remains the deterministic order produced by
    # select_direct_candidates. Unsuitable or unpermissioned candidates are
    # retained as diagnostics and never prevent a later suitable candidate
    # from filling the Direct review slot.

    rejections: list[dict[str, Any]] = []

    for raw_selection in candidates:
        post, primary_media, source = (
            dict(item)
            for item in raw_selection
        )
        source_post_id = _text(
            post.get("source_post_id")
        )
        source_id = _text(
            post.get("source_id")
            or source.get("source_id")
        )
        permission = _active_permission_row(
            permissions,
            account_id=account_id,
            source_id=source_id,
            operation="direct",
            checker=permission_checker,
        )

        if not permission:
            rejections.append(
                {
                    "source_post_id": source_post_id,
                    "source_id": source_id,
                    "status": "BLOCKED",
                    "blockers": [
                        "active_direct_permission_missing"
                    ],
                }
            )
            continue

        evidence_text, _summary, media_blockers = (
            _direct_media_evidence(primary_media)
        )
        _suitability, suitability_blockers = (
            _direct_source_suitability(
                account_id=account_id,
                post=post,
                media_evidence_text=evidence_text,
            )
        )
        blockers = sorted(
            {
                _text(reason)
                for reason in (
                    list(media_blockers)
                    + list(suitability_blockers)
                )
                if _text(reason)
            }
        )

        if blockers:
            rejections.append(
                {
                    "source_post_id": source_post_id,
                    "source_id": source_id,
                    "status": "SOURCE_EVIDENCE_UNSUITABLE",
                    "blockers": blockers,
                }
            )
            continue

        return (
            (post, primary_media, source),
            permission,
            rejections,
        )

    return None, {}, rejections


def select_source_suitable_clip_candidate(
    *,
    selector: Callable[..., tuple[
        dict[str, Any] | None,
        dict[str, Any] | None,
        dict[str, Any] | None,
        list[str],
    ]],
    clips: Sequence[Mapping[str, Any]],
    source_videos: Sequence[Mapping[str, Any]],
    media_assets: Sequence[Mapping[str, Any]],
    posted_results: Sequence[Mapping[str, Any]],
    permissions: Sequence[Mapping[str, Any]],
    account_id: str,
    permission_checker: Callable[..., bool],
) -> tuple[
    tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ]
    | None,
    dict[str, Any],
    list[dict[str, Any]],
    list[str],
]:
    # Keep the deterministic saved-media ordering, but do not let one
    # unsuitable prepared clip block a later source-suitable clip.

    excluded_clip_ids: set[str] = set()
    rejections: list[dict[str, Any]] = []
    upstream_reasons: set[str] = set()
    maximum_attempts = max(
        1,
        len(media_assets) + 1,
    )

    for _attempt in range(maximum_attempts):
        (
            clip,
            source_video,
            asset,
            selection_reasons,
        ) = selector(
            list(clips),
            list(source_videos),
            list(media_assets),
            list(posted_results),
            account_id,
            excluded_clip_ids=excluded_clip_ids,
        )

        upstream_reasons.update(
            _text(reason)
            for reason in selection_reasons
            if _text(reason)
        )

        if (
            clip is None
            or source_video is None
            or asset is None
        ):
            return (
                None,
                {},
                rejections,
                sorted(upstream_reasons),
            )

        clip = dict(clip)
        source_video = dict(source_video)
        asset = dict(asset)

        clip_id = _text(
            clip.get("clip_candidate_id")
            or clip.get("clip_id")
        )
        source_video_id = _text(
            source_video.get("source_video_id")
            or clip.get("source_video_id")
        )
        source_id = _text(
            source_video.get("source_id")
            or clip.get("source_id")
        )
        media_asset_id = _media_id(asset)

        if not clip_id:
            rejections.append(
                {
                    "clip_candidate_id": "",
                    "source_video_id": source_video_id,
                    "source_id": source_id,
                    "media_asset_id": media_asset_id,
                    "status": "BLOCKED",
                    "blockers": [
                        "clip_candidate_id_missing"
                    ],
                }
            )
            return (
                None,
                {},
                rejections,
                sorted(upstream_reasons),
            )

        if clip_id in excluded_clip_ids:
            rejections.append(
                {
                    "clip_candidate_id": clip_id,
                    "source_video_id": source_video_id,
                    "source_id": source_id,
                    "media_asset_id": media_asset_id,
                    "status": "BLOCKED",
                    "blockers": [
                        "clip_selector_repeated_excluded_candidate"
                    ],
                }
            )
            return (
                None,
                {},
                rejections,
                sorted(upstream_reasons),
            )

        permission = _active_permission_row(
            permissions,
            account_id=account_id,
            source_id=source_id,
            operation="clip",
            checker=permission_checker,
        )

        blockers: list[str] = []

        if not permission:
            blockers.append(
                "active_clip_permission_missing"
            )

        evidence_text, _summary, media_blockers = (
            _clip_media_evidence(
                clip,
                source_video,
                asset,
            )
        )
        _suitability, suitability_blockers = (
            _clip_source_suitability(
                account_id=account_id,
                transcript=evidence_text,
            )
        )

        blockers.extend(media_blockers)
        blockers.extend(suitability_blockers)
        blockers = sorted(
            {
                _text(reason)
                for reason in blockers
                if _text(reason)
            }
        )

        if blockers:
            rejections.append(
                {
                    "clip_candidate_id": clip_id,
                    "source_video_id": source_video_id,
                    "source_id": source_id,
                    "media_asset_id": media_asset_id,
                    "status": (
                        "SOURCE_EVIDENCE_UNSUITABLE"
                        if _source_evidence_blockers(
                            blockers
                        )
                        else "BLOCKED"
                    ),
                    "blockers": blockers,
                }
            )
            excluded_clip_ids.add(clip_id)
            continue

        return (
            (clip, source_video, asset),
            permission,
            rejections,
            sorted(upstream_reasons),
        )

    return (
        None,
        {},
        rejections,
        sorted(
            upstream_reasons
            | {"clip_fallback_attempt_limit_reached"}
        ),
    )


def _runtime_direct_caption_builder() -> CaptionBuilder:
    from generation.source_grounded_caption import (
        GitHubModelsGroundedProvider,
        SourceGroundedCaptionService,
        build_source_post_bundle,
    )

    service = SourceGroundedCaptionService(
        GitHubModelsGroundedProvider(),
        allow_deterministic_fallback=True,
        retry_primary_on_alignment_failure=False,
    )

    def build(packet: dict[str, Any], recent_posts: list[str]) -> dict[str, Any]:
        primary = packet["primary_media"]
        bundle_rows = _media_bundle(primary)
        source_bundle = build_source_post_bundle(packet["post"], bundle_rows)
        result = service.generate(
            source_bundle,
            account_id=packet["account_id"],
            recent_posts=recent_posts,
            transcript_excerpt=packet["media_evidence_text"],
            source_mode="source_copyedit",
        )
        text = _text(result.get("public_post_text"))
        result["public_post_hash"] = _sha_text(text) if text else ""
        return result

    return build


def _runtime_clip_caption_builder() -> CaptionBuilder:
    from run_media_production_pipeline import _generate_final_media_caption

    def build(packet: dict[str, Any], recent_posts: list[str]) -> dict[str, Any]:
        result = _generate_final_media_caption(
            clip=packet["clip"],
            source_video=packet["source_video"],
            media_asset=packet["asset"],
            account_id=packet["account_id"],
            recent_posts=recent_posts,
            max_attempts=3,
        )
        text = _text(result.get("public_post_text"))
        result["public_post_hash"] = _sha_text(text) if text else ""
        return result

    return build


def _read_records(client: Any, logical: str) -> list[dict[str, Any]]:
    from sheets_client import TAB_DEFINITIONS
    from sheets_record_reader import read_records_safely

    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    return [dict(row) for row in read_records_safely(client, logical)]


def load_production_evidence_plan(batch_id: str) -> dict[str, Any]:
    from config_loader import get_config
    from final_production_contracts import is_active_permission
    from generation.source_copyedit import validate_source_preserving_public_post
    from generation_quality_gates import evaluate_generation_quality, topic_coherence_validator
    from media_post_validator import validate_media_post
    from prepare_media_activation_candidates import build_plan, candidate_blockers
    from public_post_quality import final_public_post_validator
    from run_direct_reference_media_pipeline import select_direct_candidates
    from run_media_production_pipeline import select_saved_media_candidate
    from sheets_client import SheetsClient

    config = get_config()
    client = SheetsClient(config["sheet_id"], config["sa_dict"], dry_run=True)
    datasets = {
        logical: _read_records(client, logical)
        for logical in (
            "queue",
            "media_permissions",
            "video_clip_candidates",
            "source_videos",
            "media_assets",
            "posted_results",
        )
    }
    direct_selections: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None] = {}
    clip_selections: dict[str, tuple[dict[str, Any], dict[str, Any], dict[str, Any]] | None] = {}
    permission_map: dict[tuple[str, str], dict[str, Any]] = {}
    direct_selection_diagnostics: dict[str, dict[str, Any]] = {}
    clip_selection_diagnostics: dict[str, dict[str, Any]] = {}
    for account_id in ACCOUNTS:
        direct_candidates, direct_reasons = select_direct_candidates(
            client,
            account_id,
        )
        (
            direct_selection,
            direct_permission,
            selection_rejections,
        ) = select_source_suitable_direct_candidate(
            direct_candidates,
            permissions=datasets["media_permissions"],
            account_id=account_id,
            permission_checker=is_active_permission,
        )
        direct_selections[account_id] = direct_selection
        selected_source_post_id = (
            _text(direct_selection[0].get("source_post_id"))
            if direct_selection is not None
            else ""
        )
        direct_selection_diagnostics[account_id] = {
            "status": (
                "PASS"
                if direct_selection is not None
                else "BLOCKED"
            ),
            "candidate_count": len(direct_candidates),
            "selected_source_post_id": selected_source_post_id,
            "rejections": selection_rejections,
            "upstream_reasons": sorted(
                {
                    _text(reason)
                    for reason in direct_reasons
                    if _text(reason)
                }
            ),
        }
        if direct_selection is not None:
            permission_map[
                (account_id, "direct_reference_media")
            ] = direct_permission
        (
            clip_selection,
            clip_permission,
            clip_rejections,
            clip_upstream_reasons,
        ) = select_source_suitable_clip_candidate(
            selector=select_saved_media_candidate,
            clips=datasets["video_clip_candidates"],
            source_videos=datasets["source_videos"],
            media_assets=datasets["media_assets"],
            posted_results=datasets["posted_results"],
            permissions=datasets["media_permissions"],
            account_id=account_id,
            permission_checker=is_active_permission,
        )
        clip_selections[account_id] = clip_selection
        selected_clip_id = (
            _text(
                clip_selection[0].get(
                    "clip_candidate_id"
                )
                or clip_selection[0].get("clip_id")
            )
            if clip_selection is not None
            else ""
        )
        clip_selection_diagnostics[account_id] = {
            "status": (
                "PASS"
                if clip_selection is not None
                else "BLOCKED"
            ),
            "selected_clip_candidate_id": (
                selected_clip_id
            ),
            "rejections": clip_rejections,
            "upstream_reasons": clip_upstream_reasons,
        }
        if clip_selection is not None:
            permission_map[
                (account_id, "approved_source_clip")
            ] = clip_permission

    report = build_review_evidence_plan(
        direct_selections=direct_selections,
        clip_selections=clip_selections,
        permissions=permission_map,
        queue_rows=datasets["queue"],
        posted_results=datasets["posted_results"],
        batch_id=batch_id,
        direct_caption_builder=_runtime_direct_caption_builder(),
        clip_caption_builder=_runtime_clip_caption_builder(),
        direct_public_validator=validate_source_preserving_public_post,
        clip_public_validator=final_public_post_validator,
        media_validator=validate_media_post,
        quality_evaluator=evaluate_generation_quality,
        topic_validator=topic_coherence_validator,
        candidate_validator=candidate_blockers,
        activation_planner=build_plan,
    )
    report["direct_selection_diagnostics"] = (
        direct_selection_diagnostics
    )
    report["clip_selection_diagnostics"] = (
        clip_selection_diagnostics
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    unsafe = safety_blockers()
    if unsafe:
        print(json.dumps({"status": "BLOCKED_UNSAFE_ENV", "blocked_reasons": unsafe}))
        return 1
    if not args.use_sheets:
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["--use-sheets is required"]}))
        return 1
    batch_id = _text(args.batch_id)
    if not batch_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in batch_id):
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["invalid_batch_id"]}))
        return 1

    report = load_production_evidence_plan(batch_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=== MEDIA ACTIVATION REVIEW EVIDENCE ===")
    print(f"READ_STATUS={report['read_status']}")
    print(f"EVIDENCE_STATUS={report['status']}")
    print(f"BATCH_ID={report['batch_id']}")
    print(f"CANDIDATE_COUNT={report['candidate_count']}")
    print(f"MISSING_SOURCE_SLOTS={','.join(report['missing_source_slots'])}")
    for account_id, item in sorted(
        report.get(
            "direct_selection_diagnostics",
            {},
        ).items()
    ):
        rejected = [
            (
                f"{row.get('source_post_id', '')}:"
                + "|".join(row.get("blockers", []))
            )
            for row in item.get("rejections", [])
        ]
        print(
            "DIRECT_SELECTION:"
            f"{account_id}:"
            f"status={item.get('status', '')}:"
            f"candidate_count={item.get('candidate_count', 0)}:"
            f"selected={item.get('selected_source_post_id', '')}:"
            f"rejected={';'.join(rejected) or 'NONE'}"
        )
    for account_id, item in sorted(
        report.get(
            "clip_selection_diagnostics",
            {},
        ).items()
    ):
        rejected = [
            (
                f"{row.get('clip_candidate_id', '')}:"
                + "|".join(row.get("blockers", []))
            )
            for row in item.get("rejections", [])
        ]
        print(
            "CLIP_SELECTION:"
            f"{account_id}:"
            f"status={item.get('status', '')}:"
            f"selected={item.get('selected_clip_candidate_id', '')}:"
            f"rejected={';'.join(rejected) or 'NONE'}"
        )
    for item in report.get("candidate_diagnostics", []):
        print(
            "SLOT:"
            f"{item.get('account_id', '')}:"
            f"{item.get('content_route', '')}:"
            f"status={item.get('status', '')}:"
            f"blockers={'|'.join(item.get('blockers', [])) or 'NONE'}:"
            f"public_hash={item.get('public_post_hash', '')}:"
            f"media_evidence_hash={item.get('media_evidence_hash', '')}:"
            f"source_evidence_status={item.get('source_evidence_status', '')}"
        )
    for row in report.get("candidates", []):
        print(
            "CANDIDATE:"
            f"{row.get('account_id', '')}:"
            f"{row.get('content_route', '')}:"
            f"status={row.get('status', '')}:"
            f"auto_publish={row.get('auto_publish', '')}:"
            f"canary_id={row.get('canary_id', '')}"
        )
    print(f"ACTIVATION_PLAN_STATUS={report.get('activation_plan', {}).get('status', 'BLOCKED')}")
    print(f"REPORT={args.output}")
    print("PASS: Production reads and local deterministic generation only")
    print("PASS: no Sheets write, permission mutation, media operation, READY transition, workflow dispatch or post")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
