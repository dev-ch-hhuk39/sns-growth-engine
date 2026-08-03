#!/usr/bin/env python3
"""Inventory every existing media-activation source without mutating Production.

The inventory joins all direct-parent and saved-clip records before applying
permission gates.  This is intentionally different from the runtime selectors,
which must discard permissionless or incomplete records.  The report classifies
existing candidates as ready for review-evidence generation, requiring a human
permission decision, requiring source repair, unsuitable, or excluded.

No function in this module grants permission, generates captions, prepares
media, writes Sheets, creates queue rows, promotes READY, dispatches workflows,
or publishes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

ACCOUNTS = ("night_scout", "liver_manager")
ROUTES = ("direct_reference_media", "approved_source_clip")

READY = "READY_FOR_REVIEW_EVIDENCE"
PERMISSION_REVIEW = "PERMISSION_REVIEW_REQUIRED"
SOURCE_REPAIR = "SOURCE_REPAIR_REQUIRED"
UNSUITABLE = "SOURCE_EVIDENCE_UNSUITABLE"
EXCLUDED = "EXCLUDED"

STATUS_ORDER = {
    READY: 0,
    PERMISSION_REVIEW: 1,
    SOURCE_REPAIR: 2,
    UNSUITABLE: 3,
    EXCLUDED: 4,
}

ACTIVE_QUEUE_STATUSES = {
    "WAITING_REVIEW",
    "READY",
    "MEDIA_READY",
    "PROCESSING",
}
READY_CLIP_STATUSES = {"READY", "AUTO_APPROVED", "MEDIA_READY"}
APPROVED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}

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

PermissionChecker = Callable[..., bool]
QuarantineChecker = Callable[[Mapping[str, Any]], bool]
VideoEvidenceChecker = Callable[[Mapping[str, Any]], bool]
IndividualURLChecker = Callable[[str, str], bool]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _true(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "pass"}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _sha_text(value: Any) -> str:
    text = _text(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_time(value: Any) -> datetime | None:
    text = _text(value).replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _excerpt(value: Any, limit: int = 260) -> str:
    text = " ".join(_text(value).replace("\r", " ").replace("\n", " ").split())
    return text if len(text) <= limit else text[:limit] + "..."


def safety_blockers(environ: Mapping[str, str] | None = None) -> list[str]:
    source = os.environ if environ is None else environ
    return [f"{name}=true" for name in DANGEROUS_ENV if _true(source.get(name))]


def _compact_japanese(value: Any) -> str:
    return "".join(_text(value).split()).casefold()


def _account_evidence_hits(account_id: str, value: Any) -> list[str]:
    compact = _compact_japanese(value)
    return sorted(
        {
            term
            for term in ACCOUNT_EVIDENCE_TERMS.get(account_id, ())
            if term.casefold() in compact
        }
    )


def _source_text_packet(account_id: str, original: Any) -> dict[str, Any]:
    raw = _text(original)
    cleaned = re.sub(r"https?://\S+", "", raw)
    cleaned = re.sub(r"(?<!\S)[@#]\S+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    compact = re.sub(r"[\s\W_]+", "", cleaned, flags=re.UNICODE)
    usable = (
        len(compact) >= 20
        and bool(re.search(r"[ぁ-んァ-ヶ一-龠々]", cleaned))
    )
    return {
        "hash": _sha_text(cleaned),
        "length": len(cleaned),
        "usable": usable,
        "account_terms": _account_evidence_hits(account_id, cleaned),
        "excerpt": _excerpt(cleaned),
    }


def _media_id(row: Mapping[str, Any]) -> str:
    return _text(
        row.get("media_asset_id")
        or row.get("media_id")
        or row.get("source_post_media_id")
    )


def _media_url(row: Mapping[str, Any]) -> str:
    return _text(row.get("storage_url") or row.get("cloudinary_url"))


def _permission_id(row: Mapping[str, Any]) -> str:
    return _text(row.get("permission_id") or row.get("media_permission_id"))


def _default_quarantined(row: Mapping[str, Any]) -> bool:
    statuses = (
        row.get("status"),
        row.get("clip_status"),
        row.get("reviewer_status"),
        row.get("post_status"),
    )
    return bool(
        _text(row.get("quarantined_at"))
        or _text(row.get("quarantine_reason"))
        or any(_text(value).upper() == "QUARANTINED" for value in statuses)
    )


def _default_video_evidence(row: Mapping[str, Any]) -> bool:
    return (
        _number(row.get("video_stream_count")) >= 1
        and _text(row.get("media_probe_status")).upper() == "PASS"
    )


def _default_individual_url(platform: str, url: str) -> bool:
    value = _text(url).lower()
    platform = _text(platform).lower()
    if platform == "tiktok":
        return "tiktok.com/" in value and "/video/" in value
    if platform == "youtube":
        return (
            "youtube.com/watch" in value
            or "youtube.com/shorts/" in value
            or "youtu.be/" in value
        )
    if platform == "threads":
        return "threads.com/" in value and "/post/" in value
    if platform == "x":
        return ("x.com/" in value or "twitter.com/" in value) and "/status/" in value
    return False


def _synthetic_identity(*rows: Mapping[str, Any]) -> bool:
    """Reject legacy generated canary parents as well as generated assets.

    Direct-source inventory operates before runtime permission filters, so the
    synthetic marker may exist only on the parent/source identity rather than
    on a linked media asset.  Inspect both identity and provenance fields.
    """

    values: list[str] = []
    for row in rows:
        for field in (
            "source_post_id",
            "source_id",
            "source_video_id",
            "media_asset_id",
            "media_id",
            "source_post_media_id",
            "clip_candidate_id",
            "clip_id",
            "platform",
            "source_platform",
            "collection_backend",
            "resolver_backend",
            "backend_version",
            "generated_by",
            "provider_name",
            "media_origin",
            "source_type",
            "notes",
        ):
            values.append(_text(row.get(field)).lower())
    joined = "|".join(values)
    return any(
        marker in joined
        for marker in (
            "fresh_remaining_eight",
            "remaining_eight",
            "system_generated",
            "system-generated",
            "system_owned",
            "system-owned",
            "pillow+ffmpeg",
            "synthetic",
            "generated_clip",
        )
    )


def _active_permission(
    permissions: Sequence[Mapping[str, Any]],
    *,
    account_id: str,
    source_id: str,
    operation: str,
    checker: PermissionChecker,
) -> dict[str, Any]:
    rows = [
        dict(row)
        for row in permissions
        if _text(row.get("source_id")) == source_id
        and checker(dict(row), account_id=account_id, operation=operation)
    ]
    rows.sort(
        key=lambda row: (
            _text(row.get("updated_at") or row.get("approved_at")),
            _permission_id(row),
        ),
        reverse=True,
    )
    return rows[0] if rows else {}


def _permission_scope_missing(permission: Mapping[str, Any], route: str) -> list[str]:
    if not permission:
        return ["active_permission_missing"]
    required = (
        (
            "allow_cloudinary_storage",
            "allow_original_repost",
            "allow_new_caption",
        )
        if route == "direct_reference_media"
        else (
            "allow_cloudinary_storage",
            "allow_cut",
            "allow_clip_repost",
            "allow_new_caption",
        )
    )
    return [field for field in required if not _true(permission.get(field))]


def _direct_asset_for_media(
    media: Mapping[str, Any],
    assets: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    original_url = _text(media.get("original_media_url"))
    media_row_id = _text(media.get("source_post_media_id"))
    exact_url = [
        dict(row)
        for row in assets
        if original_url and _text(row.get("original_media_url")) == original_url
    ]
    if exact_url:
        exact_url.sort(
            key=lambda row: _text(row.get("uploaded_at") or row.get("created_at")),
            reverse=True,
        )
        return exact_url[0]
    exact_child = [
        dict(row)
        for row in assets
        if media_row_id
        and _text(row.get("source_post_media_id")) == media_row_id
    ]
    if exact_child:
        exact_child.sort(
            key=lambda row: _text(row.get("uploaded_at") or row.get("created_at")),
            reverse=True,
        )
        return exact_child[0]
    return dict(assets[0]) if len(assets) == 1 else {}


def _direct_media_packet(
    media_rows: Sequence[Mapping[str, Any]],
    assets: Sequence[Mapping[str, Any]],
    understanding_by_media: Mapping[str, Mapping[str, Any]],
    *,
    quarantine_checker: QuarantineChecker,
    posted_asset_ids: set[str],
    queued_asset_ids: set[str],
) -> dict[str, Any]:
    evidence_parts: list[str] = []
    items: list[dict[str, Any]] = []
    repair: list[str] = []
    exclusions: list[str] = []

    sorted_media = sorted(
        (dict(row) for row in media_rows),
        key=lambda row: int(_number(row.get("media_index"), 0)),
    )

    for media in sorted_media:
        asset = _direct_asset_for_media(media, assets)
        merged = {
            **media,
            **{
                key: value
                for key, value in asset.items()
                if _text(value)
            },
        }
        media_row_id = _text(media.get("source_post_media_id"))
        understanding = dict(understanding_by_media.get(media_row_id, {}))
        evidence_values = [
            _text(understanding.get("visual_summary")),
            _text(understanding.get("visible_text")),
            _text(understanding.get("ocr_text")),
            _text(understanding.get("transcript_text")),
        ]
        evidence_values = [value for value in evidence_values if value]
        evidence_parts.extend(evidence_values)
        media_id = _media_id(merged)
        media_type = _text(merged.get("media_type")).lower()
        upload_status = _text(
            merged.get("cloudinary_status") or merged.get("upload_status")
        ).upper()
        persisted = upload_status == "UPLOADED" and bool(_media_url(merged))
        understanding_pass = _text(understanding.get("status")).upper() == "PASS"

        if quarantine_checker(media) or quarantine_checker(asset):
            exclusions.append(f"{media_row_id or media_id or 'media'}:quarantined")
        if _synthetic_identity(media, asset):
            exclusions.append(f"{media_row_id or media_id or 'media'}:synthetic_media_forbidden")
        if media_id and (media_id in posted_asset_ids or media_id in queued_asset_ids):
            exclusions.append(f"{media_id}:already_used")
        if _text(merged.get("reuse_status")).upper() == "POSTED":
            exclusions.append(f"{media_id or media_row_id}:reuse_status_posted")
        if not understanding_pass:
            repair.append(f"{media_row_id or media_id or 'media'}:media_understanding_not_pass")
        if not evidence_values:
            repair.append(f"{media_row_id or media_id or 'media'}:media_understanding_empty")
        if not asset:
            repair.append(f"{media_row_id or 'media'}:persisted_asset_link_missing")
        if not persisted:
            repair.append(f"{media_id or media_row_id or 'media'}:media_not_uploaded")
        if media_type not in {"video", "image"}:
            exclusions.append(
                f"{media_id or media_row_id or 'media'}:unsupported_media_type"
            )
        if media_type == "video" and _number(merged.get("duration_seconds")) > 300:
            exclusions.append(
                f"{media_id or media_row_id or 'media'}:video_duration_above_direct_limit"
            )

        items.append(
            {
                "source_post_media_id": media_row_id,
                "media_asset_id": media_id,
                "media_type": media_type,
                "media_url_present": bool(_media_url(merged)),
                "upload_status": upload_status,
                "persisted": persisted,
                "understanding_status": _text(understanding.get("status")).upper(),
                "understanding_hash": _sha_text("\n".join(evidence_values)),
            }
        )

    if not sorted_media:
        repair.append("source_post_media_missing")
    evidence_text = "\n".join(evidence_parts).strip()
    if not evidence_text:
        repair.append("direct_media_evidence_missing")

    return {
        "items": items,
        "item_count": len(items),
        "evidence_text": evidence_text,
        "evidence_hash": _sha_text(evidence_text),
        "account_terms_by_account": {
            account_id: _account_evidence_hits(account_id, evidence_text)
            for account_id in ACCOUNTS
        },
        "repair_blockers": sorted(set(repair)),
        "exclusion_blockers": sorted(set(exclusions)),
        "all_understanding_pass": bool(items) and all(
            item["understanding_status"] == "PASS" for item in items
        ),
        "all_persisted": bool(items) and all(item["persisted"] for item in items),
    }


def _direct_state(
    *,
    source_packet: Mapping[str, Any],
    media_packet: Mapping[str, Any],
    active_permission: Mapping[str, Any],
    permission_scope_missing: Sequence[str],
    extra_exclusions: Sequence[str],
) -> tuple[str, list[str]]:
    exclusions = sorted(
        set(media_packet.get("exclusion_blockers", [])) | set(extra_exclusions)
    )
    repair = list(media_packet.get("repair_blockers", []))
    source_terms = list(source_packet.get("account_terms", []))
    media_terms = list(
        media_packet.get("account_terms_by_account", {}).get(
            source_packet.get("account_id", ""),
            [],
        )
    )
    shared = sorted(set(source_terms) & set(media_terms))
    unsuitable: list[str] = []
    if not source_packet.get("usable"):
        unsuitable.append("direct_source_post_text_unusable")
    if len(source_terms) < MIN_SOURCE_EVIDENCE_TERM_COUNT:
        unsuitable.append("direct_source_account_evidence_insufficient")
    if media_packet.get("all_understanding_pass"):
        if len(media_terms) < MIN_SOURCE_EVIDENCE_TERM_COUNT:
            unsuitable.append("direct_media_account_evidence_insufficient")
        if source_terms and media_terms and not shared:
            unsuitable.append("direct_source_media_topic_mismatch")
    if exclusions:
        return EXCLUDED, exclusions + unsuitable + repair
    if unsuitable:
        return UNSUITABLE, sorted(set(unsuitable + repair))
    if repair:
        return SOURCE_REPAIR, sorted(set(repair))
    if not active_permission or permission_scope_missing:
        return PERMISSION_REVIEW, sorted(
            set(
                ["active_direct_permission_missing"]
                if not active_permission
                else []
            )
            | {f"permission_scope_missing:{field}" for field in permission_scope_missing}
        )
    return READY, []


def _direct_score(
    state: str,
    source_packet: Mapping[str, Any],
    media_packet: Mapping[str, Any],
    *,
    permission_active: bool,
    source_priority: Any,
) -> float:
    source_terms = list(source_packet.get("account_terms", []))
    account_id = _text(source_packet.get("account_id"))
    media_terms = list(
        media_packet.get("account_terms_by_account", {}).get(account_id, [])
    )
    shared = set(source_terms) & set(media_terms)
    score = 0.0
    score += 30 if source_packet.get("usable") else 0
    score += min(25, len(source_terms) * 5)
    score += min(25, len(media_terms) * 5)
    score += min(10, len(shared) * 5)
    score += 10 if media_packet.get("all_understanding_pass") else 0
    score += 10 if media_packet.get("all_persisted") else 0
    score += 10 if permission_active else 0
    score += max(-10, min(10, _number(source_priority)))
    score -= {READY: 0, PERMISSION_REVIEW: 5, SOURCE_REPAIR: 30, UNSUITABLE: 60, EXCLUDED: 100}[state]
    return round(score, 2)


def build_direct_inventory(
    *,
    account_id: str,
    source_posts: Sequence[Mapping[str, Any]],
    source_post_media: Sequence[Mapping[str, Any]],
    media_assets: Sequence[Mapping[str, Any]],
    source_media_understanding: Sequence[Mapping[str, Any]],
    source_accounts: Sequence[Mapping[str, Any]],
    reference_sources: Sequence[Mapping[str, Any]],
    permissions: Sequence[Mapping[str, Any]],
    queue_rows: Sequence[Mapping[str, Any]],
    posted_results: Sequence[Mapping[str, Any]],
    permission_checker: PermissionChecker,
    quarantine_checker: QuarantineChecker = _default_quarantined,
    individual_url_checker: IndividualURLChecker = _default_individual_url,
) -> list[dict[str, Any]]:
    sources = {
        _text(row.get("source_id")): dict(row)
        for row in list(source_accounts) + list(reference_sources)
        if _text(row.get("source_id"))
    }
    media_by_post: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in source_post_media:
        media_by_post[_text(row.get("source_post_id"))].append(dict(row))
    assets_by_post: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in media_assets:
        post_id = _text(row.get("reference_post_id") or row.get("source_post_id"))
        if post_id:
            assets_by_post[post_id].append(dict(row))
    understanding_by_media = {
        _text(row.get("source_post_media_id")): dict(row)
        for row in source_media_understanding
        if _text(row.get("source_post_media_id"))
    }
    posted_asset_ids = {
        _text(row.get("media_asset_id") or row.get("media_id"))
        for row in posted_results
        if _text(row.get("status")).upper() == "POSTED"
    }
    posted_source_post_ids = {
        _text(row.get("source_post_id"))
        for row in posted_results
        if _text(row.get("status")).upper() == "POSTED"
    }
    queued_asset_ids = {
        _text(row.get("media_asset_id"))
        for row in queue_rows
        if _text(row.get("status")).upper() in ACTIVE_QUEUE_STATUSES
    }
    queued_source_post_ids = {
        _text(row.get("source_post_id"))
        for row in queue_rows
        if _text(row.get("status")).upper() in ACTIVE_QUEUE_STATUSES
    }

    results: list[dict[str, Any]] = []
    for post in source_posts:
        target_account = _text(post.get("target_account_id") or post.get("account_id"))
        if target_account != account_id:
            continue
        post = dict(post)
        post_id = _text(post.get("source_post_id"))
        source_id = _text(post.get("source_id"))
        source = sources.get(source_id, {})
        platform = _text(
            post.get("platform")
            or source.get("platform")
            or source.get("source_platform")
        ).lower()
        source_url = _text(
            post.get("canonical_post_url")
            or post.get("post_url")
        )
        source_packet = _source_text_packet(account_id, post.get("original_post_text"))
        source_packet["account_id"] = account_id
        media_packet = _direct_media_packet(
            media_by_post.get(post_id, []),
            assets_by_post.get(post_id, []),
            understanding_by_media,
            quarantine_checker=quarantine_checker,
            posted_asset_ids=posted_asset_ids,
            queued_asset_ids=queued_asset_ids,
        )
        permission = _active_permission(
            permissions,
            account_id=account_id,
            source_id=source_id,
            operation="direct",
            checker=permission_checker,
        )
        scope_missing = _permission_scope_missing(permission, "direct_reference_media")
        extra_exclusions: list[str] = []
        if quarantine_checker(post) or quarantine_checker(source):
            extra_exclusions.append("source_post_or_source_quarantined")
        if post_id in posted_source_post_ids or post_id in queued_source_post_ids:
            extra_exclusions.append("source_post_already_used")
        if _synthetic_identity(post, source):
            extra_exclusions.append("synthetic_source_forbidden")
        if not post_id:
            extra_exclusions.append("source_post_id_missing")
        if not source_url or not individual_url_checker(platform, source_url):
            extra_exclusions.append("individual_source_post_url_required")
        state, blockers = _direct_state(
            source_packet=source_packet,
            media_packet=media_packet,
            active_permission=permission,
            permission_scope_missing=scope_missing,
            extra_exclusions=extra_exclusions,
        )
        hard_blockers = sorted(
            set(media_packet.get("exclusion_blockers", []))
            | set(extra_exclusions)
        )
        repair_blockers = list(media_packet.get("repair_blockers", []))
        media_terms = media_packet["account_terms_by_account"].get(account_id, [])
        shared_terms = sorted(set(source_packet["account_terms"]) & set(media_terms))
        score = _direct_score(
            state,
            source_packet,
            media_packet,
            permission_active=bool(permission) and not scope_missing,
            source_priority=source.get("priority"),
        )
        results.append(
            {
                "account_id": account_id,
                "content_route": "direct_reference_media",
                "candidate_status": state,
                "candidate_score": score,
                "source_post_id": post_id,
                "source_id": source_id,
                "source_url": source_url,
                "platform": platform,
                "published_at": _text(post.get("published_at")),
                "source_priority": source.get("priority", ""),
                "permission_id": _permission_id(permission),
                "permission_active": bool(permission),
                "permission_scope_missing": scope_missing,
                "human_approval_required": state == PERMISSION_REVIEW,
                "source_text": source_packet,
                "media": {
                    key: value
                    for key, value in media_packet.items()
                    if key != "evidence_text"
                },
                "source_account_terms": source_packet["account_terms"],
                "media_account_terms": media_terms,
                "shared_account_terms": shared_terms,
                "hard_blockers": hard_blockers,
                "repair_blockers": repair_blockers,
                "blockers": sorted(set(blockers)),
                "external_operations": [],
            }
        )
    return _sort_candidates(results)


def _clip_asset_score(
    row: Mapping[str, Any],
    *,
    quarantine_checker: QuarantineChecker,
    video_evidence_checker: VideoEvidenceChecker,
) -> tuple[int, str, str]:
    uploaded = _text(row.get("upload_status") or row.get("cloudinary_status")).upper() == "UPLOADED"
    persisted = uploaded and bool(_media_url(row))
    valid_video = video_evidence_checker(row)
    safe = not quarantine_checker(row) and not _synthetic_identity(row)
    score = int(persisted) * 4 + int(valid_video) * 3 + int(safe) * 2
    return score, _text(row.get("uploaded_at") or row.get("created_at")), _media_id(row)


def _clip_state(
    *,
    clip: Mapping[str, Any],
    source_video: Mapping[str, Any],
    asset: Mapping[str, Any],
    account_id: str,
    active_permission: Mapping[str, Any],
    permission_scope_missing: Sequence[str],
    quarantine_checker: QuarantineChecker,
    video_evidence_checker: VideoEvidenceChecker,
    individual_url_checker: IndividualURLChecker,
    already_used: bool,
) -> tuple[str, list[str], dict[str, Any]]:
    transcript = _text(clip.get("transcript_excerpt") or clip.get("transcript_text"))
    compact = _compact_japanese(transcript)
    terms = _account_evidence_hits(account_id, transcript)
    source_packet = {
        "transcript_hash": _sha_text(transcript),
        "transcript_compact_length": len(compact),
        "transcript_excerpt": _excerpt(transcript, 500),
        "account_terms": terms,
        "minimum_account_term_count": MIN_SOURCE_EVIDENCE_TERM_COUNT,
        "minimum_transcript_chars": MIN_CLIP_TRANSCRIPT_CHARS,
    }
    exclusions: list[str] = []
    repair: list[str] = []
    unsuitable: list[str] = []
    if quarantine_checker(clip) or quarantine_checker(source_video) or quarantine_checker(asset):
        exclusions.append("clip_source_or_asset_quarantined")
    if _synthetic_identity(clip, source_video, asset):
        exclusions.append("synthetic_media_forbidden")
    if already_used:
        exclusions.append("clip_or_asset_already_used")

    source_video_id = _text(source_video.get("source_video_id") or clip.get("source_video_id"))
    if not source_video_id:
        repair.append("source_video_missing")
    platform = _text(source_video.get("platform")).lower()
    source_url = _text(source_video.get("canonical_video_url") or source_video.get("source_video_url"))
    if not source_url or not individual_url_checker(platform, source_url):
        repair.append("individual_source_video_url_required")
    if not _true(clip.get("transcript_grounded")):
        repair.append("transcript_grounding_required")
    if not transcript:
        repair.append("transcript_excerpt_missing")
    if not _text(clip.get("start_seconds") or clip.get("start_time")):
        repair.append("clip_start_missing")
    if not _text(clip.get("end_seconds") or clip.get("end_time")):
        repair.append("clip_end_missing")
    clip_status = _text(
        clip.get("clip_status") or clip.get("reviewer_status") or clip.get("post_status")
    ).upper()
    if clip_status not in READY_CLIP_STATUSES:
        repair.append("clip_not_ready")
    if not asset:
        repair.append("linked_media_asset_missing")
    else:
        upload_status = _text(asset.get("upload_status") or asset.get("cloudinary_status")).upper()
        if upload_status != "UPLOADED" or not _media_url(asset):
            repair.append("media_asset_not_uploaded")
        if not video_evidence_checker(asset):
            repair.append("media_stream_evidence_missing")
    if transcript and _true(clip.get("transcript_grounded")):
        if len(compact) < MIN_CLIP_TRANSCRIPT_CHARS:
            unsuitable.append("clip_transcript_too_short_for_grounding")
        if len(terms) < MIN_SOURCE_EVIDENCE_TERM_COUNT:
            unsuitable.append("clip_account_evidence_insufficient")

    if exclusions:
        return EXCLUDED, sorted(set(exclusions + repair + unsuitable)), source_packet
    if unsuitable:
        return UNSUITABLE, sorted(set(unsuitable + repair)), source_packet
    if repair:
        return SOURCE_REPAIR, sorted(set(repair)), source_packet
    if not active_permission or permission_scope_missing:
        blockers = []
        if not active_permission:
            blockers.append("active_clip_permission_missing")
        blockers.extend(f"permission_scope_missing:{field}" for field in permission_scope_missing)
        return PERMISSION_REVIEW, sorted(set(blockers)), source_packet
    return READY, [], source_packet


def _clip_score(
    state: str,
    source_packet: Mapping[str, Any],
    *,
    asset_ready: bool,
    permission_ready: bool,
    confidence: Any,
) -> float:
    score = 0.0
    score += min(30, len(source_packet.get("account_terms", [])) * 10)
    score += min(20, _number(source_packet.get("transcript_compact_length")) / 5)
    score += 20 if asset_ready else 0
    score += 10 if permission_ready else 0
    score += max(0, min(20, _number(confidence) * 20))
    score -= {READY: 0, PERMISSION_REVIEW: 5, SOURCE_REPAIR: 30, UNSUITABLE: 60, EXCLUDED: 100}[state]
    return round(score, 2)


def build_clip_inventory(
    *,
    account_id: str,
    clips: Sequence[Mapping[str, Any]],
    source_videos: Sequence[Mapping[str, Any]],
    media_assets: Sequence[Mapping[str, Any]],
    permissions: Sequence[Mapping[str, Any]],
    queue_rows: Sequence[Mapping[str, Any]],
    posted_results: Sequence[Mapping[str, Any]],
    permission_checker: PermissionChecker,
    quarantine_checker: QuarantineChecker = _default_quarantined,
    video_evidence_checker: VideoEvidenceChecker = _default_video_evidence,
    individual_url_checker: IndividualURLChecker = _default_individual_url,
) -> list[dict[str, Any]]:
    videos = {
        _text(row.get("source_video_id")): dict(row)
        for row in source_videos
        if _text(row.get("source_video_id"))
    }
    assets_by_clip: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in media_assets:
        clip_id = _text(row.get("clip_candidate_id") or row.get("video_clip_id"))
        if clip_id:
            assets_by_clip[clip_id].append(dict(row))
    posted_clips = {
        _text(row.get("clip_candidate_id"))
        for row in posted_results
        if _text(row.get("status")).upper() == "POSTED"
    }
    posted_assets = {
        _text(row.get("media_asset_id") or row.get("media_id"))
        for row in posted_results
        if _text(row.get("status")).upper() == "POSTED"
    }
    queued_clips = {
        _text(row.get("clip_candidate_id") or row.get("video_clip_id"))
        for row in queue_rows
        if _text(row.get("status")).upper() in ACTIVE_QUEUE_STATUSES
    }
    queued_assets = {
        _text(row.get("media_asset_id"))
        for row in queue_rows
        if _text(row.get("status")).upper() in ACTIVE_QUEUE_STATUSES
    }

    results: list[dict[str, Any]] = []
    for clip_row in clips:
        clip = dict(clip_row)
        clip_id = _text(clip.get("clip_candidate_id") or clip.get("clip_id"))
        source_video = videos.get(_text(clip.get("source_video_id") or clip.get("reference_post_id")), {})
        candidate_account = _text(
            clip.get("account_id")
            or clip.get("target_account_id")
            or source_video.get("account_id")
            or source_video.get("target_account_id")
        )
        if candidate_account != account_id:
            continue
        linked_assets = assets_by_clip.get(clip_id, [])
        linked_assets.sort(
            key=lambda row: _clip_asset_score(
                row,
                quarantine_checker=quarantine_checker,
                video_evidence_checker=video_evidence_checker,
            ),
            reverse=True,
        )
        asset = dict(linked_assets[0]) if linked_assets else {}
        source_id = _text(source_video.get("source_id") or clip.get("source_id"))
        permission = _active_permission(
            permissions,
            account_id=account_id,
            source_id=source_id,
            operation="clip",
            checker=permission_checker,
        )
        scope_missing = _permission_scope_missing(permission, "approved_source_clip")
        media_id = _media_id(asset)
        already_used = (
            clip_id in posted_clips
            or clip_id in queued_clips
            or media_id in posted_assets
            or media_id in queued_assets
        )
        state, blockers, source_packet = _clip_state(
            clip=clip,
            source_video=source_video,
            asset=asset,
            account_id=account_id,
            active_permission=permission,
            permission_scope_missing=scope_missing,
            quarantine_checker=quarantine_checker,
            video_evidence_checker=video_evidence_checker,
            individual_url_checker=individual_url_checker,
            already_used=already_used,
        )
        asset_ready = bool(asset) and (
            _text(asset.get("upload_status") or asset.get("cloudinary_status")).upper() == "UPLOADED"
            and bool(_media_url(asset))
            and video_evidence_checker(asset)
        )
        score = _clip_score(
            state,
            source_packet,
            asset_ready=asset_ready,
            permission_ready=bool(permission) and not scope_missing,
            confidence=clip.get("confidence_score") or clip.get("clip_score"),
        )
        results.append(
            {
                "account_id": account_id,
                "content_route": "approved_source_clip",
                "candidate_status": state,
                "candidate_score": score,
                "clip_candidate_id": clip_id,
                "source_video_id": _text(source_video.get("source_video_id") or clip.get("source_video_id")),
                "source_id": source_id,
                "source_url": _text(source_video.get("canonical_video_url") or source_video.get("source_video_url")),
                "platform": _text(source_video.get("platform")).lower(),
                "media_asset_id": media_id,
                "linked_media_asset_count": len(linked_assets),
                "media_url_present": bool(_media_url(asset)),
                "asset_upload_status": _text(asset.get("upload_status") or asset.get("cloudinary_status")).upper(),
                "asset_video_evidence": video_evidence_checker(asset) if asset else False,
                "permission_id": _permission_id(permission),
                "permission_active": bool(permission),
                "permission_scope_missing": scope_missing,
                "human_approval_required": state == PERMISSION_REVIEW,
                "source_evidence": source_packet,
                "blockers": sorted(set(blockers)),
                "external_operations": [],
            }
        )
    return _sort_candidates(results)


def _identity(row: Mapping[str, Any]) -> str:
    return _text(row.get("source_post_id") or row.get("clip_candidate_id"))


def _sort_candidates(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = [dict(row) for row in rows]
    result.sort(
        key=lambda row: (
            STATUS_ORDER.get(_text(row.get("candidate_status")), 99),
            -_number(row.get("candidate_score")),
            _identity(row),
        )
    )
    return result


def summarize_slot(
    account_id: str,
    route: str,
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    ordered = _sort_candidates(candidates)
    counts = Counter(_text(row.get("candidate_status")) for row in ordered)
    selected: dict[str, Any] = {}
    route_status = "NEW_SOURCE_REQUIRED"
    next_action = "ACQUIRE_NEW_ACCOUNT_ALIGNED_APPROVED_SOURCE"
    for state, status, action in (
        (READY, "EXISTING_SOURCE_READY", "RUN_REVIEW_EVIDENCE_BUILDER_READ_ONLY"),
        (PERMISSION_REVIEW, "HUMAN_PERMISSION_REVIEW_REQUIRED", "HUMAN_PERMISSION_LEDGER_DECISION"),
        (SOURCE_REPAIR, "EXISTING_SOURCE_REPAIR_REQUIRED", "REPAIR_EXISTING_SOURCE_EVIDENCE"),
    ):
        selected = next((dict(row) for row in ordered if row.get("candidate_status") == state), {})
        if selected:
            route_status = status
            next_action = action
            break
    top_audit = dict(ordered[0]) if ordered else {}
    return {
        "account_id": account_id,
        "content_route": route,
        "route_status": route_status,
        "next_action": next_action,
        "candidate_count": len(ordered),
        "status_counts": {key: counts.get(key, 0) for key in STATUS_ORDER},
        "recommended_candidate_id": _identity(selected),
        "recommended_candidate_status": _text(selected.get("candidate_status")),
        "recommended_candidate_score": selected.get("candidate_score", ""),
        "recommended_candidate_blockers": list(selected.get("blockers", [])),
        "top_audit_candidate_id": _identity(top_audit),
        "top_audit_candidate_status": _text(top_audit.get("candidate_status")),
        "human_approval_required": route_status == "HUMAN_PERMISSION_REVIEW_REQUIRED",
        "external_operations": [],
    }


def build_source_inventory(
    *,
    datasets: Mapping[str, Sequence[Mapping[str, Any]]],
    permission_checker: PermissionChecker,
    quarantine_checker: QuarantineChecker = _default_quarantined,
    video_evidence_checker: VideoEvidenceChecker = _default_video_evidence,
    individual_url_checker: IndividualURLChecker = _default_individual_url,
) -> dict[str, Any]:
    direct: dict[str, list[dict[str, Any]]] = {}
    clips: dict[str, list[dict[str, Any]]] = {}
    slots: list[dict[str, Any]] = []
    for account_id in ACCOUNTS:
        direct[account_id] = build_direct_inventory(
            account_id=account_id,
            source_posts=datasets.get("source_posts", []),
            source_post_media=datasets.get("source_post_media", []),
            media_assets=datasets.get("media_assets", []),
            source_media_understanding=datasets.get("source_media_understanding", []),
            source_accounts=datasets.get("source_accounts", []),
            reference_sources=datasets.get("reference_sources", []),
            permissions=datasets.get("media_permissions", []),
            queue_rows=datasets.get("queue", []),
            posted_results=datasets.get("posted_results", []),
            permission_checker=permission_checker,
            quarantine_checker=quarantine_checker,
            individual_url_checker=individual_url_checker,
        )
        clips[account_id] = build_clip_inventory(
            account_id=account_id,
            clips=datasets.get("video_clip_candidates", []),
            source_videos=datasets.get("source_videos", []),
            media_assets=datasets.get("media_assets", []),
            permissions=datasets.get("media_permissions", []),
            queue_rows=datasets.get("queue", []),
            posted_results=datasets.get("posted_results", []),
            permission_checker=permission_checker,
            quarantine_checker=quarantine_checker,
            video_evidence_checker=video_evidence_checker,
            individual_url_checker=individual_url_checker,
        )
        slots.append(
            summarize_slot(account_id, "direct_reference_media", direct[account_id])
        )
        slots.append(
            summarize_slot(account_id, "approved_source_clip", clips[account_id])
        )
    all_candidates = [
        *[row for account_id in ACCOUNTS for row in direct[account_id]],
        *[row for account_id in ACCOUNTS for row in clips[account_id]],
    ]
    new_source_slots = [
        f"{row['account_id']}:{row['content_route']}"
        for row in slots
        if row["route_status"] == "NEW_SOURCE_REQUIRED"
    ]
    permission_review_slots = [
        f"{row['account_id']}:{row['content_route']}"
        for row in slots
        if row["route_status"] == "HUMAN_PERMISSION_REVIEW_REQUIRED"
    ]
    repair_slots = [
        f"{row['account_id']}:{row['content_route']}"
        for row in slots
        if row["route_status"] == "EXISTING_SOURCE_REPAIR_REQUIRED"
    ]
    ready_slots = [
        f"{row['account_id']}:{row['content_route']}"
        for row in slots
        if row["route_status"] == "EXISTING_SOURCE_READY"
    ]
    status = (
        "PASS_EXISTING_SOURCES_READY"
        if len(ready_slots) == 4
        else "BLOCKED_SOURCE_OR_PERMISSION_REPAIR_REQUIRED"
    )
    return {
        "status": status,
        "read_status": "READ_ONLY_COMPLETE",
        "required_slot_count": 4,
        "ready_slot_count": len(ready_slots),
        "permission_review_slot_count": len(permission_review_slots),
        "repair_slot_count": len(repair_slots),
        "new_source_slot_count": len(new_source_slots),
        "ready_slots": ready_slots,
        "permission_review_slots": permission_review_slots,
        "repair_slots": repair_slots,
        "new_source_slots": new_source_slots,
        "total_candidate_count": len(all_candidates),
        "slots": slots,
        "candidates": {
            account_id: {
                "direct_reference_media": direct[account_id],
                "approved_source_clip": clips[account_id],
            }
            for account_id in ACCOUNTS
        },
        "planned_external_operations": [],
        "safety": {
            "production_write": False,
            "sheets_write": False,
            "permission_mutation": False,
            "caption_generation": False,
            "evidence_mutation": False,
            "media_download": False,
            "media_cut": False,
            "media_upload": False,
            "queue_write": False,
            "ready_transition": False,
            "workflow_dispatch": False,
            "sns_post": False,
        },
    }


def _read_records(client: Any, logical: str) -> list[dict[str, Any]]:
    from sheets_client import TAB_DEFINITIONS
    from sheets_record_reader import read_records_safely

    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    return [dict(row) for row in read_records_safely(client, logical)]


def load_production_inventory() -> dict[str, Any]:
    from acquisition.reliability import is_quarantined
    from config_loader import get_config
    from final_production_contracts import (
        is_active_permission,
        is_individual_source_post_url,
    )
    from media.media_probe import asset_has_video_evidence
    from sheets_client import SheetsClient

    config = get_config()
    client = SheetsClient(config["sheet_id"], config["sa_dict"], dry_run=True)
    logical_names = (
        "queue",
        "media_permissions",
        "video_clip_candidates",
        "source_videos",
        "media_assets",
        "posted_results",
        "source_posts",
        "source_accounts",
        "reference_sources",
        "source_post_media",
        "source_media_understanding",
    )
    datasets = {name: _read_records(client, name) for name in logical_names}
    return build_source_inventory(
        datasets=datasets,
        permission_checker=is_active_permission,
        quarantine_checker=is_quarantined,
        video_evidence_checker=asset_has_video_evidence,
        individual_url_checker=is_individual_source_post_url,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    unsafe = safety_blockers()
    if unsafe:
        print(json.dumps({"status": "BLOCKED_UNSAFE_ENV", "blocked_reasons": unsafe}))
        return 1
    if not args.use_sheets:
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["--use-sheets is required"]}))
        return 1

    report = load_production_inventory()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=== MEDIA ACTIVATION SOURCE SUITABILITY INVENTORY ===")
    print(f"READ_STATUS={report['read_status']}")
    print(f"INVENTORY_STATUS={report['status']}")
    print(f"TOTAL_CANDIDATE_COUNT={report['total_candidate_count']}")
    print(f"READY_SLOT_COUNT={report['ready_slot_count']}")
    print(f"PERMISSION_REVIEW_SLOT_COUNT={report['permission_review_slot_count']}")
    print(f"REPAIR_SLOT_COUNT={report['repair_slot_count']}")
    print(f"NEW_SOURCE_SLOT_COUNT={report['new_source_slot_count']}")
    for slot in report["slots"]:
        print(
            "SLOT:"
            f"{slot['account_id']}:"
            f"{slot['content_route']}:"
            f"status={slot['route_status']}:"
            f"candidate_count={slot['candidate_count']}:"
            f"recommended={slot['recommended_candidate_id'] or 'NONE'}:"
            f"recommended_status={slot['recommended_candidate_status'] or 'NONE'}:"
            f"next_action={slot['next_action']}"
        )
        rows = report["candidates"][slot["account_id"]][slot["content_route"]]
        for row in rows[:5]:
            print(
                "CANDIDATE:"
                f"{slot['account_id']}:"
                f"{slot['content_route']}:"
                f"id={_identity(row)}:"
                f"status={row['candidate_status']}:"
                f"score={row['candidate_score']}:"
                f"permission={row.get('permission_id', '') or 'NONE'}:"
                f"blockers={'|'.join(row.get('blockers', [])) or 'NONE'}"
            )
    print(f"READY_SLOTS={','.join(report['ready_slots'])}")
    print(f"PERMISSION_REVIEW_SLOTS={','.join(report['permission_review_slots'])}")
    print(f"REPAIR_SLOTS={','.join(report['repair_slots'])}")
    print(f"NEW_SOURCE_SLOTS={','.join(report['new_source_slots'])}")
    print(f"PLANNED_EXTERNAL_OPERATIONS={','.join(report['planned_external_operations'])}")
    print(f"REPORT={args.output}")
    print("PASS: Production and Sheets read-only inventory")
    print("PASS: no permission inference, generation, media operation, queue write, dispatch or post")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
