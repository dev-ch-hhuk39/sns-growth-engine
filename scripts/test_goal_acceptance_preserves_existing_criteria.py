#!/usr/bin/env python3
"""Keep the original Goal contract immutable while allowing additive criteria."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_PATH = ROOT / "config" / "goal_acceptance.json"

ORIGINAL_CRITERIA_IDS = {
    "repository_public",
    "secret_history_scan",
    "production_secrets_private",
    "github_hosted_only",
    "no_vps_or_self_hosted_dependency",
    "working_tree_clean",
    "origin_main_matches",
    "agent_reach_integrated",
    "last30days_integrated",
    "youtube_backends_integrated",
    "tiktok_multiple_backends_integrated",
    "threads_multiple_backends_integrated",
    "web_fallback_integrated",
    "library_capability_matrix_complete",
    "night_account_url_discovery",
    "night_source_bundle",
    "night_direct_media_post",
    "night_approved_source_clip_post",
    "night_caption_alignment",
    "liver_account_url_discovery",
    "liver_source_bundle",
    "liver_direct_media_post",
    "liver_approved_source_clip_post",
    "liver_caption_alignment",
    "permission_single_authority",
    "backend_failover",
    "asset_quarantine",
    "next_candidate_selection",
    "schedule_delay_recovery",
    "slot_idempotency",
    "sheets_evidence",
    "cloudinary_idempotency",
    "text_fallback",
    "text_pipeline_regression_free",
    "all_required_tests_pass",
}

ADDITIVE_CRITERIA_IDS = {
    "dual_account_capability_matrix",
    "account_persona_all_paths",
    "independent_dual_account_schedules",
    "media_slots_no_text_fallback",
    "source_parent_identity_integrity",
    "direct_media_type_coverage",
    "approved_source_clip_end_to_end",
    "publisher_read_after_write",
    "retry_and_slot_idempotency",
    "metrics_lifecycle",
    "pdca_uses_actual_metrics",
    "production_repair_completion",
    "dual_account_canary_eight_posts",
}


def main() -> None:
    acceptance = json.loads(ACCEPTANCE_PATH.read_text(encoding="utf-8"))
    ids = [criterion["id"] for criterion in acceptance["criteria"]]
    assert len(ids) == len(set(ids)), "criterion IDs must be unique"
    assert ORIGINAL_CRITERIA_IDS.issubset(ids), "the original 35 criteria changed"
    assert ADDITIVE_CRITERIA_IDS.issubset(ids), "required additive criteria missing"
    assert len(ids) == 48, "criteria must be 35 original + 13 additive"
    print("PASS test_goal_acceptance_preserves_existing_criteria.py")


if __name__ == "__main__":
    main()
