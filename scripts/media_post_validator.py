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

APPROVED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}
DIRECT_REFERENCE_MAX_VIDEO_SECONDS = 300


def validate_media_post(plan: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    rights = str(plan.get("rights_status", "")).lower()
    account_id = str(plan.get("account_id", ""))
    platform = str(plan.get("platform", "")).lower()
    text = plan.get("public_post_text", "")
    text_result = final_public_post_validator(text, account_id)
    duration = float(plan.get("duration_seconds") or 0)
    aspect = str(plan.get("aspect_ratio", ""))
    media_origin = str(plan.get("media_origin", "generated_clip")).strip().lower()
    alignment_status = str(plan.get("alignment_status", "")).upper()
    try:
        final_alignment = float(plan.get("final_alignment_score") or 0)
        claim_coverage = float(plan.get("main_claim_coverage") or 0)
        unsupported_claims = int(float(plan.get("unsupported_claim_count") or 0))
        copy_similarity = float(plan.get("source_copy_similarity") or 1)
        recent_similarity = float(plan.get("recent_post_similarity") or 1)
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
    if media_type not in {"video", "image"}:
        reasons.append("media_type_not_supported")
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
            if aspect != "9:16":
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
    if copy_similarity > ALIGNMENT_THRESHOLDS["source_copy_similarity"]:
        reasons.append("source_copy_similarity_above_threshold")
    if recent_similarity > ALIGNMENT_THRESHOLDS["recent_post_similarity"]:
        reasons.append("recent_post_similarity_above_threshold")
    return {
        "status": "PASS" if not reasons else "BLOCKED",
        "blocked_reasons": sorted(set(reasons)),
        "text_validation": text_result["status"],
        "alignment_validation": "PASS" if not any(reason.startswith(("semantic_alignment", "final_alignment", "main_claim", "unsupported_claim", "source_copy", "recent_post")) for reason in reasons) else "BLOCKED",
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
