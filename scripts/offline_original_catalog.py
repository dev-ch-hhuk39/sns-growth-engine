"""Finite account-owned fallback copy; never accepts arbitrary queue text."""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
CATALOG_VERSION = "offline_original_v1"
ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")


def requests_offline_review(queue: Mapping[str, Any]) -> bool:
    try:
        policy = json.loads(str(queue.get("generation_policy_json") or "{}"))
    except (ValueError, TypeError):
        return False
    return isinstance(policy, dict) and "offline_original" in policy


@lru_cache(maxsize=3)
def catalog(account_id: str) -> tuple[str, ...]:
    if account_id not in ACCOUNTS:
        return ()
    from public_post_quality import generate_production_post, generate_reader_facing_post

    texts = []
    path = ROOT / "config/offline_original_posts.json"
    if path.exists():
        texts.extend(json.loads(path.read_text(encoding="utf-8")).get(account_id, []))
    for index in range(25):
        if account_id != "beauty_account":
            texts.append(generate_reader_facing_post(account_id, index + 1).get("public_post_text", ""))
    for index in range(192):
        texts.append(generate_production_post(
            account_id, batch_id=CATALOG_VERSION, content_type="original_text", attempt=index,
        ).get("public_post_text", ""))
    distinct = list(dict.fromkeys(text for text in texts if isinstance(text, str) and text.strip()))
    return tuple(_paragraph_layout(text, index, account_id) for index, text in enumerate(distinct))


def _paragraph_layout(text: str, index: int, account_id: str = "") -> str:
    """Assign one stable readable layout to each distinct article, not variants of it."""
    paragraphs = text.split("\n\n")
    if len(paragraphs) != 3 or index % 3 == 0:
        return text
    if index % 3 == 1:
        if account_id == "beauty_account":
            ending = paragraphs[2].split("\n", 1)
            return "\n\n".join(paragraphs[:2] + ending)
        return paragraphs[0] + "\n" + paragraphs[1] + "\n\n" + paragraphs[2]
    units = re.split(r"(?<=。)|\n", paragraphs[1], maxsplit=1)
    if len(units) == 2 and all(unit.strip() for unit in units):
        return "\n\n".join([paragraphs[0], units[0], units[1], paragraphs[2]])
    return text


def evidence(account_id: str, text: str) -> dict[str, str]:
    return {"version": CATALOG_VERSION, "account_id": account_id,
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def offline_original_reasons(queue: Mapping[str, Any]) -> list[str]:
    account = str(queue.get("account_id", ""))
    text = str(queue.get("public_post_text", ""))
    reasons = []
    if account not in ACCOUNTS or str(queue.get("target_account_id") or account) != account:
        reasons.append("offline_account_not_allowed")
    if str(queue.get("platform", "")).lower() != "threads":
        reasons.append("offline_platform_not_allowed")
    if str(queue.get("content_type", "")) not in {"original_text", "new_text_generation"}:
        reasons.append("offline_original_text_only")
    if str(queue.get("generation_mode", "")) not in {"original_text", "new_text_generation"}:
        reasons.append("offline_original_generation_only")
    if any(str(queue.get(key) or "").strip() for key in (
        "source_id", "source_post_id", "source_video_id", "source_url", "clip_candidate_id",
        "media_asset_id", "media_url", "media_urls_json", "pdca_result_id", "source_result_id",
    )) or str(queue.get("media_required", "")).lower() in {"true", "1", "yes"}:
        reasons.append("offline_source_or_media_not_allowed")
    try:
        policy = json.loads(str(queue.get("generation_policy_json") or "{}"))
    except (ValueError, TypeError):
        policy = {}
    if not isinstance(policy, dict):
        policy = {}
    if policy.get("offline_original") != evidence(account, text) or text not in catalog(account):
        reasons.append("offline_catalog_evidence_mismatch")
    previous = policy.get("hybrid_ai_gate", {})
    if isinstance(previous, dict) and previous.get("provider_mode") == "gemini" and previous.get("status") == "BLOCKED":
        reasons.append("offline_semantic_rejection_not_overridable")
    return reasons


def select_original(account_id: str, history: list[Any], *, batch_compared: list[Any] | None = None) -> dict[str, Any]:
    from generation_quality_gates import evaluate_generation_quality
    from public_post_quality import final_public_post_validator
    from auto_approve_queue import near_duplicate, normalize_text

    history = [row for row in history if not isinstance(row, dict)
               or str(row.get("account_id") or row.get("target_account_id") or account_id) == account_id]
    old_texts = [str(row.get("public_post_text") or row.get("posted_text") or "")
                 if isinstance(row, dict) else str(row) for row in history]
    used = {normalize_text(text) for text in old_texts}
    for text in catalog(account_id):
        if normalize_text(text) in used:
            continue
        public = final_public_post_validator(text, account_id)
        if public["status"] != "PASS":
            continue
        quality = evaluate_generation_quality(account_id, text, history, batch_compared=batch_compared or [])
        if quality["status"] != "PASS" or near_duplicate(text, old_texts):
            continue
        return {"public_post_text": text, "generation_provider": CATALOG_VERSION,
                "generation_policy": {"offline_original": evidence(account_id, text)},
                "post_design": {}, "grounding_summary": {}, "quality": quality}
    return {}
