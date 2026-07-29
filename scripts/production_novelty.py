"""Fail-closed novelty checks shared by canary and scheduled preparation."""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from generation.semantic_alignment import lexical_similarity


def normalized_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip().lower()


def text_hash(value: Any) -> str:
    return hashlib.sha256(normalized_text(value).encode("utf-8")).hexdigest()


def evaluate_candidate_novelty(
    *,
    account_id: str,
    public_post_text: str,
    recent_posts: list[dict[str, Any]] | list[str],
    pending_queue: list[dict[str, Any]] | list[str],
    media_hashes: list[str] | None = None,
    used_media_hashes: set[str] | None = None,
    used_public_ids: set[str] | None = None,
    threshold: float = 0.75,
) -> dict[str, Any]:
    """Return evidence for a candidate before it can become READY.

    Exact text and asset identities are hard blocks. Lexical Japanese similarity
    is a bounded local semantic proxy; callers regenerate rather than weakening
    the final publisher idempotency gate.
    """
    candidate_hash = text_hash(public_post_text)
    historical_texts: list[str] = []
    pending_texts: list[str] = []
    for item in recent_posts:
        if isinstance(item, dict) and str(item.get("account_id", "")) not in {"", account_id}:
            continue
        historical_texts.append(str(item.get("posted_text", "") if isinstance(item, dict) else item))
    for item in pending_queue:
        if isinstance(item, dict) and str(item.get("account_id", "")) not in {"", account_id}:
            continue
        pending_texts.append(str(item.get("public_post_text", "") if isinstance(item, dict) else item))
    exact_posted = any(text_hash(item) == candidate_hash for item in historical_texts if normalized_text(item))
    exact_queue = any(text_hash(item) == candidate_hash for item in pending_texts if normalized_text(item))
    similarity = max((lexical_similarity(public_post_text, item) for item in historical_texts + pending_texts if normalized_text(item)), default=0.0)
    duplicate_hashes = sorted({value for value in (media_hashes or []) if value and value in (used_media_hashes or set())})
    duplicate_public_ids = sorted({value for value in (used_public_ids or set()) if value})
    reasons: list[str] = []
    if exact_posted:
        reasons.append("posted_results_exact_text_match")
    if exact_queue:
        reasons.append("queue_exact_text_match")
    if similarity > threshold:
        reasons.append("recent_semantic_similarity_above_threshold")
    if duplicate_hashes:
        reasons.append("media_content_hash_already_used")
    if duplicate_public_ids:
        reasons.append("media_public_id_already_used")
    return {
        "status": "PASS" if not reasons else "BLOCKED",
        "text_hash": candidate_hash,
        "exact_posted_match": exact_posted,
        "exact_queue_match": exact_queue,
        "recent_semantic_similarity": round(similarity, 4),
        "semantic_similarity_threshold": threshold,
        "duplicate_media_hashes": duplicate_hashes,
        "duplicate_public_ids": duplicate_public_ids,
        "blocked_reasons": reasons,
    }
