#!/usr/bin/env python3
"""Build the final human-reviewed twelve-item production canary plan.

This command never reads credentials, mutates Sheets, fetches media, or posts.
It describes the exact evidence each approved candidate must have before a
single-item manual canary can be dispatched.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CANARY_TYPES = ("original_text", "reference_text", "direct_image", "direct_video", "direct_carousel", "generated_clip")
FIRST_WAVE_TYPES = ("original_text", "direct_image")
ACCOUNTS = ("night_scout", "liver_manager")
QUALITY_GATE_VERSION = "generation_quality_v3"
TOPIC_CONFIDENCE_MIN = 0.70


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "pass"}


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def required_fields(canary_type: str) -> tuple[str, ...]:
    common = ("account_id", "source_id", "rights_status", "permission_status", "permission_evidence", "public_post_text")
    quality = (
        "batch_id", "batch_diversity_status", "topic_coherence_status",
        "primary_topic", "topic_confidence", "structure_variant", "hook_topic_match",
        "closing_topic_match", "quality_gate_version",
    )
    if canary_type in {"original_text", "reference_text"}:
        return (
            "account_id", "public_post_text", "queue_id",
            "persona_validator_status", "final_public_post_validator_status",
            "internal_leak_status",
        ) + quality
    validated_media = (
        "queue_id", "persona_validator_status", "final_public_post_validator_status",
        "internal_leak_status", "publisher_media_type", "alignment_status",
        "final_alignment_score", "main_claim_coverage", "unsupported_claim_count",
        "source_copy_similarity", "recent_post_similarity",
        "feature_schema_version", "media_primary_topic", "visual_topic",
        "visual_topic_match", "visual_cta_match", "visual_plan_version",
        "visual_text_hash", "claim_support_json",
    ) + quality
    if canary_type == "generated_clip":
        return common + validated_media + ("source_video_id", "clip_candidate_id", "local_path", "start_seconds", "end_seconds")
    if canary_type == "direct_carousel":
        return common + validated_media + ("source_post_id", "media_asset_ids", "media_order")
    return common + validated_media + ("source_post_id", "media_asset_id", "media_url")


def build_plan(candidates: list[dict[str, Any]], *, wave: str = "all_12") -> dict[str, Any]:
    if wave not in {"all_12", "first_wave"}:
        raise ValueError("unsupported_wave")
    selected_types = FIRST_WAVE_TYPES if wave == "first_wave" else CANARY_TYPES
    rows: list[dict[str, Any]] = []
    relevant = [row for row in candidates if str(row.get("canary_type", "")) in selected_types and str(row.get("account_id", "")) in ACCOUNTS]
    batch_ids = {str(row.get("batch_id", "")).strip() for row in relevant if str(row.get("batch_id", "")).strip()}
    same_batch_ok = wave != "first_wave" or (len(relevant) == 4 and len(batch_ids) == 1)
    by_key = {(str(row.get("account_id", "")), str(row.get("canary_type", ""))): row for row in relevant}
    for account_id in ACCOUNTS:
        for canary_type in selected_types:
            candidate = dict(by_key.get((account_id, canary_type), {}))
            required = required_fields(canary_type)
            missing = [
                field for field in required
                if candidate.get(field) is None
                or (isinstance(candidate.get(field), str) and not candidate.get(field).strip())
                or candidate.get(field) == []
            ]
            is_text = canary_type in {"original_text", "reference_text"}
            rights_ok = is_text or str(candidate.get("rights_status", "")) in {"owned", "licensed", "approved_creator_clip"}
            permission_ok = is_text or str(candidate.get("permission_status", "")) == "approved"
            validator_fields = ("persona_validator_status", "final_public_post_validator_status", "internal_leak_status")
            validators_ok = all(str(candidate.get(field, "")).upper() == "PASS" for field in validator_fields)
            alignment_ok = is_text or (
                str(candidate.get("alignment_status", "")).upper() == "PASS"
                and _as_bool(candidate.get("visual_topic_match"))
                and _as_bool(candidate.get("visual_cta_match"))
                and _as_float(candidate.get("main_claim_coverage")) >= 1.0
                and int(_as_float(candidate.get("unsupported_claim_count"))) == 0
                and str(candidate.get("feature_schema_version", "")) == "post_features_v1"
                and str(candidate.get("visual_plan_version", "")) == "visual_plan_v1"
            )
            quality_ok = (
                str(candidate.get("batch_diversity_status", "")).upper() == "PASS"
                and str(candidate.get("topic_coherence_status", "")).upper() == "PASS"
                and str(candidate.get("quality_gate_version", "")) == QUALITY_GATE_VERSION
                and _as_float(candidate.get("topic_confidence")) >= TOPIC_CONFIDENCE_MIN
                and _as_bool(candidate.get("hook_topic_match"))
                and _as_bool(candidate.get("closing_topic_match"))
                and not _as_bool(candidate.get("shared_hook_detected"))
                and not _as_bool(candidate.get("shared_closing_detected"))
            )
            status = "READY_FOR_HUMAN_CANARY" if candidate and not missing and rights_ok and permission_ok and validators_ok and alignment_ok and quality_ok and same_batch_ok else "PENDING_EVIDENCE"
            rows.append({
                "canary_id": str(candidate.get("canary_id") or f"canary_{account_id}_{canary_type}"),
                "batch_id": str(candidate.get("batch_id", "")),
                "account_id": account_id,
                "canary_type": canary_type,
                "status": status,
                "missing_evidence": missing + ([] if rights_ok else ["approved_rights_status"]) + ([] if permission_ok else ["permission_status=approved"]) + ([] if validators_ok else ["media_validators=PASS"]) + ([] if alignment_ok else ["alignment_status=PASS"]) + ([] if quality_ok else ["generation_quality_gates=PASS"]) + ([] if same_batch_ok else ["exact_four_same_batch_required"]),
                "publish_limit": 1,
                "required_read_after_write": ["Threads post URL", "posted_results result_id", "media asset provenance", "metrics 24h/72h/7d jobs"],
                "rollback": "set kill_switch=true; preserve posted result; do not retry the same idempotency key",
            })
    ready_count = sum(row["status"] == "READY_FOR_HUMAN_CANARY" for row in rows)
    return {"status": "PLAN_ONLY", "wave": wave, "selected_batch_id": next(iter(batch_ids), "") if len(batch_ids) == 1 else "", "same_batch_contract": "PASS" if same_batch_ok else "BLOCKED", "total_canaries": len(rows), "ready_canaries": ready_count, "accounts": list(ACCOUNTS), "canaries": rows, "would_fetch": False, "would_write": False, "would_upload": False, "would_post": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", default="", help="optional candidate fixture; never a live Sheets read")
    parser.add_argument("--wave", choices=["all_12", "first_wave"], default="all_12")
    args = parser.parse_args()
    candidates: list[dict[str, Any]] = []
    if args.input_json:
        candidates = list(json.loads(Path(args.input_json).read_text(encoding="utf-8")).get("candidates", []))
    print(json.dumps(build_plan(candidates, wave=args.wave), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
