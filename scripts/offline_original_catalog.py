"""Finite account-owned fallback copy; never accepts arbitrary queue text."""
from __future__ import annotations

import hashlib
import json
import re
from difflib import SequenceMatcher
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
    offline_evidence = policy.get("offline_original", {})
    source_text = str(policy.get("offline_original_source_text") or text)
    source_matches = (
        offline_evidence == evidence(account, source_text)
        and source_text in catalog(account)
        and hashlib.sha256(text.encode("utf-8")).hexdigest()
        == str(policy.get("offline_original_output_hash") or offline_evidence.get("content_hash", ""))
    )
    if not source_matches:
        reasons.append("offline_catalog_evidence_mismatch")
    previous = policy.get("hybrid_ai_gate", {})
    if isinstance(previous, dict) and previous.get("provider_mode") == "gemini" and previous.get("status") == "BLOCKED":
        reasons.append("offline_semantic_rejection_not_overridable")
    return reasons


@lru_cache(maxsize=3)
def _prepared_candidates(account_id: str) -> tuple[dict[str, Any], ...]:
    """Validate and rank immutable catalog items once per account/process."""
    from generation_quality_gates import evaluate_generation_quality
    from generation.content_quality_v2 import hard_gate, rank_candidate, repair_style_only
    from public_post_quality import final_public_post_validator

    prepared: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source_text in catalog(account_id):
        repaired = repair_style_only(source_text, account_id)
        text = repaired["public_post_text"]
        key = re.sub(r"\s+", "", text).lower()
        if not key or key in seen:
            continue
        public = final_public_post_validator(text, account_id)
        gate = hard_gate({"account_id": account_id, "target_account_id": account_id,
                          "platform": "threads", "public_post_text": text},
                         account_id=account_id, public_validation=public)
        if gate["status"] != "PASS":
            continue
        quality = evaluate_generation_quality(account_id, text, [], batch_compared=[])
        rank = rank_candidate({
            "candidate_id": evidence(account_id, text)["content_hash"],
            "quality_components": {
                "reader_value": public.get("reader_value_score", 45),
                "account_relevance": public.get("account_fit_score", 45),
                "naturalness": public.get("naturalness_score", 45),
                "persona_evidence": public.get("account_fit_score", 45),
                "topic_coherence": quality.get("topic_coherence_score", 45),
                "media_caption_relevance": 45,
                "concrete_evidence": 45,
                "novelty": 100,
                "cta_fit": max(0, 100 - public.get("cta_pressure_score", 0)),
                "style_diversity": 100 if quality.get("batch_diversity_status") == "PASS" else 55,
            },
            "warnings": quality.get("diversity_blocked_reasons", [])
                + quality.get("topic_blocked_reasons", []),
        }, account_id=account_id)
        prepared.append({
            "source_text": source_text,
            "text": text,
            "repair": repaired,
            "public": public,
            "gate": gate,
            "quality": quality,
            **rank,
        })
        seen.add(key)
    prepared.sort(key=lambda row: (-float(row["quality_rank"]), evidence(account_id, row["text"])["content_hash"]))
    return tuple(prepared)


def select_original(account_id: str, history: list[Any], *, batch_compared: list[Any] | None = None,
                    used_texts: list[Any] | None = None) -> dict[str, Any]:
    from auto_approve_queue import near_duplicate, normalize_text
    from generation.content_quality_v2 import rank_candidate

    history = [row for row in history if not isinstance(row, dict)
               or str(row.get("account_id") or row.get("target_account_id") or account_id) == account_id]
    old_texts = [str(row.get("public_post_text") or row.get("posted_text") or "")
                 if isinstance(row, dict) else str(row) for row in history]
    all_used = [str(row.get("public_post_text") or row.get("posted_text") or "")
                if isinstance(row, dict) else str(row)
                for row in (used_texts or [])]
    used = {normalize_text(text) for text in old_texts + all_used if text}
    ranked: list[tuple[float, dict[str, Any]]] = []
    for candidate in _prepared_candidates(account_id):
        source_text = candidate["source_text"]
        text = candidate["text"]
        if normalize_text(text) in used:
            continue
        if near_duplicate(text, old_texts):
            continue
        similarity = max((SequenceMatcher(None, normalize_text(text), normalize_text(previous)).ratio()
                          for previous in old_texts[-40:] if previous), default=0.0)
        dynamic_rank = dict(candidate["quality_rank_components"])
        dynamic_rank["novelty"] = max(0, 100 - similarity * 100)
        validation = rank_candidate({"quality_components": dynamic_rank,
                                     "warnings": candidate["warnings"]}, account_id=account_id)
        ranked.append((float(validation["quality_rank"]), {
            "public_post_text": text,
            "generation_provider": CATALOG_VERSION,
            "generation_policy": {
                "offline_original": evidence(account_id, source_text),
                "offline_original_source_text": source_text,
                "offline_original_output_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "content_quality_v2_repair_count": candidate["repair"]["repair_count"],
            },
            "post_design": {}, "grounding_summary": {}, "quality": candidate["quality"],
            "content_quality_v2_version": "content_quality_v2",
            "content_quality_v2_status": "DRAFT_ONLY_RANKED",
            "repair_count": candidate["repair"]["repair_count"],
            "hard_gate_reasons": candidate["gate"]["hard_gate_reasons"],
            **validation,
        }))
    return max(ranked, key=lambda pair: (pair[0], pair[1]["generation_policy"]["offline_original"]["content_hash"]))[1] if ranked else {}
