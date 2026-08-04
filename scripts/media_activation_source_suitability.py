#!/usr/bin/env python3
"""Pure account-grounding contracts for Direct and approved-clip evidence."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, Sequence

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


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sha_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def compact_japanese(value: Any) -> str:
    return "".join(str(value or "").split()).casefold()


def account_evidence_hits(account_id: str, value: Any) -> list[str]:
    compact = compact_japanese(value)
    return sorted({term for term in ACCOUNT_EVIDENCE_TERMS.get(account_id, ()) if term.casefold() in compact})


def direct_source_suitability(*, account_id: str, post: Mapping[str, Any], media_evidence_text: str) -> tuple[dict[str, Any], list[str]]:
    original = _text(post.get("original_post_text"))
    cleaned = re.sub(r"https?://\S+", "", original)
    cleaned = re.sub(r"(?<!\S)[@#]\S+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    compact_source = re.sub(r"[\s\W_]+", "", cleaned, flags=re.UNICODE)
    source_usable = len(compact_source) >= 20 and bool(re.search(r"[ぁ-んァ-ヶ一-龠々]", cleaned))
    source_hits = account_evidence_hits(account_id, cleaned)
    media_hits = account_evidence_hits(account_id, media_evidence_text)
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


def clip_source_suitability(*, account_id: str, transcript: str) -> tuple[dict[str, Any], list[str]]:
    compact = compact_japanese(transcript)
    hits = account_evidence_hits(account_id, transcript)
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


def source_evidence_blockers(values: Sequence[str]) -> list[str]:
    prefixes = ("direct_source_", "direct_media_", "clip_transcript_", "clip_account_")
    return sorted({_text(value) for value in values if _text(value).startswith(prefixes)})
