#!/usr/bin/env python3
"""Pure routing policy for deterministic and Gemini-assisted post paths."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

TARGET_ACCOUNTS = {"night_scout", "liver_manager"}
GATED_GENERATION_MODES = {
    "original_text",
    "reference_text",
    "metrics_driven_pdca_text",
    "reference_score_to_threads",
    "direct_reference_media",
    "saved_direct_reference_media",
    "saved_approved_source_clip",
    "system_owned_media",
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
    if generation_mode in {"original_text", "reference_text", "metrics_driven_pdca_text", "reference_score_to_threads"}:
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
