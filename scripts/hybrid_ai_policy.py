#!/usr/bin/env python3
"""Pure routing policy for deterministic and Gemini-assisted post paths."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

from accounts.managed_accounts import managed_account_ids

TARGET_ACCOUNTS = set(managed_account_ids())
GATED_GENERATION_MODES = {
    "original_text",
    "reference_text",
    "metrics_driven_pdca_text",
    "reference_score_to_threads",
    "direct_reference_media",
    "saved_direct_reference_media",
    "saved_approved_source_clip",
    "system_owned_media",
    "safe_original_fallback_threads",
    "approved_source_clip",
    "beauty_new_text_generation",
    "beauty_reference_text_generation",
    "beauty_pdca_text_generation",
    "beauty_direct_reference_media",
    "beauty_approved_source_clip",
    "tiktok_shop_new_text_generation",
    "tiktok_shop_reference_text_generation",
    "tiktok_shop_pdca_text_generation",
    "tiktok_shop_direct_reference_media",
    "tiktok_shop_approved_source_clip",
}


@dataclass(frozen=True)
class AiRoute:
    route: str
    classify: bool
    generate: bool
    review: bool
    estimated_requests: int
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _value(record: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(record.get(key, "") or "").strip()
        if value:
            return value
    return ""


def requires_hybrid_ai_gate(candidate: Mapping[str, Any]) -> bool:
    account_id = _value(candidate, "account_id")
    if account_id not in TARGET_ACCOUNTS:
        return False
    if _value(candidate, "platform").lower() not in {"", "threads"}:
        return False
    generation_mode = _value(candidate, "generation_mode", "source_generation_mode").lower()
    media_origin = _value(candidate, "media_origin").lower()
    content_type = _value(candidate, "content_type").lower()
    return bool(
        generation_mode in GATED_GENERATION_MODES
        or media_origin in {"direct_reference", "approved_source_clip"}
        or content_type in {"direct_reference_media", "approved_source_clip"}
        or _value(candidate, "source_post_id", "source_video_id", "clip_candidate_id")
    )


def decide_route(candidate: Mapping[str, Any]) -> AiRoute:
    account_id = _value(candidate, "account_id")
    if account_id not in TARGET_ACCOUNTS:
        return AiRoute("manual_review", False, False, False, 0, "account_not_supported")
    caption_mode = _value(candidate, "caption_mode", "transformation_type", "source_generation_mode").lower()
    generation_mode = _value(candidate, "generation_mode").lower()
    media_origin = _value(candidate, "media_origin").lower()
    content_type = _value(candidate, "content_type").lower()
    ownership = _value(candidate, "ownership", "source_ownership").lower()
    source_id = _value(candidate, "source_id").lower()

    # Beauty production preparation already performs Gemini generation plus
    # deterministic persona/compliance validation.  The following Hybrid AI
    # step is a semantic review boundary, not a second writer of public text.
    # Keeping that boundary explicit prevents a review pass from introducing
    # claims or fabricated experiences into an already validated candidate.
    beauty_text_modes = {
        "beauty_new_text_generation",
        "beauty_reference_text_generation",
        "beauty_pdca_text_generation",
    }
    if (
        account_id == "beauty_account"
        and generation_mode in beauty_text_modes
        and _value(candidate, "generated_by") == "prepare_beauty_review_candidates.py"
        and _value(candidate, "semantic_voice_status").upper() == "PENDING_HYBRID_AI_REVIEW"
    ):
        return AiRoute(
            "semantic_review",
            True,
            False,
            True,
            2,
            "validated_beauty_candidate_requires_review_without_rewrite",
        )

    if caption_mode == "source_copyedit" or (
        media_origin == "direct_reference" and not (ownership in {"owned", "system_owned"} or source_id.startswith("system_owned_"))
    ):
        return AiRoute(
            "external_direct_source_copyedit",
            True,
            True,
            True,
            3,
            "classify_then_constrained_copyedit_then_review",
        )
    if media_origin == "approved_source_clip" or content_type == "approved_source_clip" or generation_mode == "saved_approved_source_clip":
        return AiRoute("approved_clip_transform", True, True, True, 3, "clip_requires_fit_generation_and_review")
    if ownership in {"owned", "system_owned"} or source_id.startswith("system_owned_"):
        return AiRoute("owned_media_transform", True, True, True, 3, "owned_media_allows_grounded_transform")
    if generation_mode in {
        "original_text", "reference_text", "metrics_driven_pdca_text", "reference_score_to_threads",
        "beauty_new_text_generation", "beauty_reference_text_generation", "beauty_pdca_text_generation",
        "tiktok_shop_new_text_generation", "tiktok_shop_reference_text_generation", "tiktok_shop_pdca_text_generation",
    }:
        return AiRoute("new_text_generation", True, True, True, 3, "text_candidate_requires_fit_generation_and_review")
    return AiRoute("semantic_review", True, False, True, 2, "unknown_candidate_requires_classification_and_review")


def estimate_requests(candidates: Iterable[Mapping[str, Any]]) -> int:
    return sum(decide_route(candidate).estimated_requests for candidate in candidates)


def chunk_candidates(candidates: list[Mapping[str, Any]], max_requests_per_batch: int = 20) -> list[dict[str, Any]]:
    if max_requests_per_batch <= 0:
        raise ValueError("max_requests_per_batch must be > 0")
    batches: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    request_count = 0
    for candidate in candidates:
        route = decide_route(candidate)
        if route.estimated_requests > max_requests_per_batch:
            raise RuntimeError("single_candidate_exceeds_batch_limit")
        if items and request_count + route.estimated_requests > max_requests_per_batch:
            batches.append({"batch_index": len(batches) + 1, "estimated_requests": request_count, "items": items})
            items = []
            request_count = 0
        items.append({"candidate": dict(candidate), "route": route.as_dict()})
        request_count += route.estimated_requests
    if items:
        batches.append({"batch_index": len(batches) + 1, "estimated_requests": request_count, "items": items})
    return batches
