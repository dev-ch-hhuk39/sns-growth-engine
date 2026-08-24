#!/usr/bin/env python3
"""Pure account-grounding contracts for Direct and approved-clip evidence."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]


def _configured_account_evidence_terms() -> dict[str, tuple[str, ...]]:
    registry = json.loads((ROOT / "config/managed_accounts.json").read_text(encoding="utf-8"))
    result: dict[str, tuple[str, ...]] = {}
    for account_id, record in registry.get("accounts", {}).items():
        config = json.loads((ROOT / str(record["account_config"])).read_text(encoding="utf-8"))
        generation = config.get("generation", {})
        terms = [str(term) for term in generation.get("domain_terms", []) if str(term).strip()]
        for values in generation.get("topic_keywords", {}).values():
            if isinstance(values, list):
                terms.extend(str(term) for term in values if str(term).strip())
        result[str(account_id)] = tuple(dict.fromkeys(terms))
    return result


ACCOUNT_EVIDENCE_TERMS = _configured_account_evidence_terms()
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
