#!/usr/bin/env python3
"""Shared Hard/Soft policy for the first autonomous media release."""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping

MEDIA_V1_ACCOUNTS = ("night_scout", "liver_manager", "beauty_account")
MEDIA_V1_ROUTES = ("direct_reference_media", "approved_source_clip")
APPROVED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}

# These public-text failures can expose private implementation details or create
# an explicit safety/compliance problem.  Style and performance signals remain
# warnings so they can be calibrated from real post-hoc feedback.
HARD_PUBLIC_REASONS = {
    "internal_terms",
    "source_metadata_or_url",
    "draft_label",
    "risk_score_above_max",
    "tiktok_shop_prohibited_claim",
}

HARD_MEDIA_REASONS = {
    "rights_status_not_approved",
    "permission_status_not_approved",
    "media_url_missing",
    "media_asset_id_missing",
    "public_post_text_missing",
    "platform_not_threads",
    "account_not_managed",
    "account_namespace_mismatch",
    "media_route_not_enabled_for_account",
    "x_publish_blocked",
    "media_type_not_supported",
    "content_type_not_supported",
    "publisher_media_type_mismatch",
    "media_stream_evidence_missing",
    "direct_reference_duration_out_of_range",
    "duration_out_of_range",
    "aspect_ratio_missing",
    "aspect_ratio_not_preserved_from_source",
    "aspect_ratio_not_9_16",
}


def text(value: Any) -> str:
    return str(value or "").strip()


def truthy(value: Any) -> bool:
    return value is True or text(value).lower() in {"1", "true", "yes", "pass"}


def is_media_candidate(row: Mapping[str, Any]) -> bool:
    route = text(row.get("content_route") or row.get("content_type")).lower()
    mode = text(row.get("generation_mode")).lower()
    return (
        route in MEDIA_V1_ROUTES
        or mode in {
            "direct_reference_media",
            "saved_direct_reference_media",
            "approved_source_clip",
            "saved_approved_source_clip",
            "system_owned_media",
        }
        or truthy(row.get("media_required"))
    )


def split_public_validation(validation: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    reasons = {text(item) for item in validation.get("blocked_reasons", []) if text(item)}
    hard = reasons & HARD_PUBLIC_REASONS
    if validation.get("requires_human_review"):
        hard.add("explicit_human_safety_review_required")
    return sorted(hard), sorted(reasons - hard)


def split_media_reasons(
    reasons: Iterable[Any],
    *,
    public_validation: Mapping[str, Any] | None = None,
) -> tuple[list[str], list[str]]:
    normalized = {text(item) for item in reasons if text(item)}
    normalized.discard("public_post_validator_blocked")
    hard = normalized & HARD_MEDIA_REASONS
    soft = normalized - hard
    if public_validation is not None:
        public_hard, public_soft = split_public_validation(public_validation)
        hard.update(public_hard)
        soft.update(public_soft)
    return sorted(hard), sorted(soft)


def warning_fields(codes: Iterable[Any]) -> dict[str, Any]:
    values = sorted({text(item) for item in codes if text(item)})
    return {
        "soft_warning_status": "WARN" if values else "PASS",
        "soft_warning_count": len(values),
        "soft_warning_codes": json.dumps(values, ensure_ascii=False, separators=(",", ":")),
        "soft_warning_summary": ",".join(values)[:500],
    }


def hard_gate_fields(reasons: Iterable[Any]) -> dict[str, Any]:
    values = sorted({text(item) for item in reasons if text(item)})
    return {
        "hard_gate_status": "BLOCKED" if values else "PASS",
        "hard_gate_blocked_reasons": json.dumps(values, ensure_ascii=False, separators=(",", ":")),
        "media_readiness_status": "BLOCKED" if values else "MEDIA_READY",
    }
