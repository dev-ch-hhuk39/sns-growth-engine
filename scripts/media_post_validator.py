#!/usr/bin/env python3
"""Validate media + public text before any Threads video post."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from public_post_quality import final_public_post_validator
from generation.semantic_alignment import ALIGNMENT_THRESHOLDS
from generation.source_copyedit import validate_source_preserving_public_post
from media.media_probe import asset_has_video_evidence

APPROVED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}
DIRECT_REFERENCE_MAX_VIDEO_SECONDS = 300


def publisher_media_type(content_type: str, media_urls: list[str] | None = None) -> str:
    """Normalize product content types before calling the Threads publisher."""
    content_type = str(content_type or "").lower()
    if content_type == "direct_carousel" or len(media_urls or []) > 1:
        return "CAROUSEL"
    if content_type in {"direct_video", "approved_source_clip"}:
        return "VIDEO"
    if content_type == "direct_image":
        return "IMAGE"
    return ""


def validate_media_post(plan: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    rights = str(plan.get("rights_status", "")).lower()
    account_id = str(plan.get("account_id", ""))
    platform = str(plan.get("platform", "")).lower()
    text = plan.get("public_post_text", "")
    caption_mode = str(
        plan.get(
            "caption_mode",
            "transform",
        )
    ).strip().lower()
    source_preserving = (
        caption_mode
        == "source_copyedit"
    )
    text_result = (
        validate_source_preserving_public_post(
            text,
            account_id,
        )
        if source_preserving
        else final_public_post_validator(
            text,
            account_id,
        )
    )
    duration = float(plan.get("duration_seconds") or 0)
    aspect = str(plan.get("aspect_ratio", ""))
    aspect_policy = str(plan.get("aspect_ratio_policy", "preserve_source")).strip().lower()
    source_aspect = str(plan.get("source_aspect_ratio", "")).strip()
    media_origin = str(plan.get("media_origin", "approved_source_clip")).strip().lower()
    content_type = str(plan.get("content_type", "")).strip().lower()
    declared_publisher_type = str(plan.get("publisher_media_type", "")).strip().upper()
    alignment_status = str(plan.get("alignment_status", "")).upper()
    def numeric(value: Any, default: float) -> float:
        if value is None or (isinstance(value, str) and not value.strip()):
            return default
        return float(value)

    copy_similarity_raw = plan.get(
        "source_copy_similarity"
    )
    copy_similarity_present = not (
        copy_similarity_raw is None
        or (
            isinstance(
                copy_similarity_raw,
                str,
            )
            and not copy_similarity_raw.strip()
        )
    )

    try:
        final_alignment = numeric(plan.get("final_alignment_score"), 0.0)
        claim_coverage = numeric(plan.get("main_claim_coverage"), 0.0)
        unsupported_claims = int(numeric(plan.get("unsupported_claim_count"), 0.0))
        copy_similarity = numeric(
            copy_similarity_raw,
            1.0,
        )
        recent_similarity = numeric(plan.get("recent_post_similarity"), 1.0)
    except (TypeError, ValueError):
        final_alignment = claim_coverage = 0.0
        unsupported_claims = 1
        copy_similarity = recent_similarity = 1.0
    if rights not in APPROVED_RIGHTS:
        reasons.append("rights_status_not_approved")
    if plan.get("permission_status") != "approved":
        reasons.append("permission_status_not_approved")
    if not plan.get("media_url"):
        reasons.append("media_url_missing")
    if not plan.get("media_asset_id"):
        reasons.append("media_asset_id_missing")
    if platform != "threads":
        reasons.append("platform_not_threads")
    if account_id not in {"liver_manager", "night_scout"}:
        reasons.append("account_not_media_enabled")
    if account_id == "beauty_account" or platform == "x":
        reasons.append("x_or_beauty_blocked")
    media_type = str(plan.get("media_type", "video")).lower()
    enforce_stream_evidence = str(
        plan.get(
            "enforce_video_stream_evidence",
            "",
        )
    ).strip().lower() in {
        "1",
        "true",
        "yes",
    }

    if media_type not in {"video", "image"}:
        reasons.append("media_type_not_supported")
    normalized_type = publisher_media_type(content_type, plan.get("media_urls") or [])
    if content_type and not normalized_type:
        reasons.append("content_type_not_supported")
    if declared_publisher_type and normalized_type and declared_publisher_type != normalized_type:
        reasons.append("publisher_media_type_mismatch")
    if (
        media_type == "video"
        and enforce_stream_evidence
        and not asset_has_video_evidence(
            plan
        )
    ):
        reasons.append(
            "media_stream_evidence_missing"
        )

    if media_type == "video":
        if media_origin == "direct_reference":
            # Original media and generated clips are different products.  The
            # clip constraints belong only to the generated-clip path; a
            # permitted original Threads/YouTube/TikTok video may be a normal
            # landscape or square post.  Keep a bounded duration ceiling so
            # we never accidentally hand an unbounded long-form asset to the
            # publishing worker.
            # Cloudinary validates the uploaded file type before this path.
            # Older imported records can lack a persisted duration; that is
            # not evidence that the approved original is unsafe. Reject an
            # explicitly known oversized original, but let the Threads API
            # validate an otherwise approved video with missing metadata.
            if duration > DIRECT_REFERENCE_MAX_VIDEO_SECONDS:
                reasons.append("direct_reference_duration_out_of_range")
        else:
            if not 8 <= duration <= 45:
                reasons.append("duration_out_of_range")
            if aspect_policy == "preserve_source":
                if not aspect:
                    reasons.append("aspect_ratio_missing")
                elif source_aspect and aspect != source_aspect:
                    reasons.append("aspect_ratio_not_preserved_from_source")
            elif aspect != "9:16":
                reasons.append("aspect_ratio_not_9_16")
    if text_result["status"] != "PASS":
        reasons.append("public_post_validator_blocked")
    if alignment_status != "PASS":
        reasons.append("semantic_alignment_not_passed")
    if final_alignment < ALIGNMENT_THRESHOLDS["final_alignment_score"]:
        reasons.append("final_alignment_score_below_threshold")
    if claim_coverage < ALIGNMENT_THRESHOLDS["main_claim_coverage"]:
        reasons.append("main_claim_coverage_below_threshold")
    if unsupported_claims != ALIGNMENT_THRESHOLDS["unsupported_claim_count"]:
        reasons.append("unsupported_claims_present")
    if source_preserving:
        if not copy_similarity_present:
            reasons.append(
                "source_preservation_similarity_missing"
            )
        elif (
            copy_similarity
            < ALIGNMENT_THRESHOLDS[
                "source_preservation_similarity"
            ]
        ):
            reasons.append(
                "source_preservation_similarity_below_threshold"
            )
    elif (
        copy_similarity
        > ALIGNMENT_THRESHOLDS[
            "source_copy_similarity"
        ]
    ):
        reasons.append(
            "source_copy_similarity_above_threshold"
        )
    if recent_similarity > ALIGNMENT_THRESHOLDS["recent_post_similarity"]:
        reasons.append("recent_post_similarity_above_threshold")
    return {
        "status": "PASS" if not reasons else "BLOCKED",
        "blocked_reasons": sorted(set(reasons)),
        "text_validation": text_result["status"],
        "alignment_validation": "PASS" if not any(reason.startswith(("semantic_alignment", "final_alignment", "main_claim", "unsupported_claim", "source_copy", "source_preservation", "recent_post")) for reason in reasons) else "BLOCKED",
        "publisher_media_type": normalized_type,
        "caption_mode": caption_mode,
        "source_preserving": source_preserving,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="validate media post plan")
    parser.add_argument("--json", default="")
    args = parser.parse_args()
    plan = json.loads(args.json) if args.json else {}
    result = validate_media_post(plan)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
