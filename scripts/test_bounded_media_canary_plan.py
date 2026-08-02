#!/usr/bin/env python3

from build_bounded_media_canary_plan import (
    build_plan,
)

QUALITY = {
    "batch_id": "fresh_test",
    "batch_diversity_status": "PASS",
    "topic_coherence_status": "PASS",
    "primary_topic": "work_conditions",
    "topic_confidence": 0.75,
    "structure_variant": 0,
    "hook_topic_match": True,
    "closing_topic_match": True,
    "shared_hook_detected": False,
    "shared_closing_detected": False,
    "quality_gate_version": (
        "generation_quality_v3"
    ),
}

MEDIA = {
    "feature_schema_version": (
        "post_features_v1"
    ),
    "media_primary_topic": (
        "work_conditions"
    ),
    "visual_topic": "work_conditions",
    "visual_topic_match": True,
    "visual_cta_match": True,
    "visual_plan_version": (
        "visual_plan_v1"
    ),
    "visual_text_hash": "visual-hash",
    "claim_support_json": (
        '[{"verified": true}]'
    ),
}

empty = build_plan([])

assert empty["total_canaries"] == 10

direct = {
    "account_id": "night_scout",
    "canary_type": (
        "direct_reference_media"
    ),
    "source_id": "s",
    "rights_status": "owned",
    "permission_status": "approved",
    "permission_evidence": "ledger",
    "public_post_text": (
        "読者向けの自然な投稿文です。"
    ),
    "queue_id": "q",
    "persona_validator_status": "PASS",
    (
        "final_public_post_"
        "validator_status"
    ): "PASS",
    "internal_leak_status": "PASS",
    "publisher_media_type": "VIDEO",
    "alignment_status": "PASS",
    "final_alignment_score": 1,
    "main_claim_coverage": 1,
    "unsupported_claim_count": 0,
    "source_copy_similarity": 0,
    "recent_post_similarity": 0,
    "source_post_id": "p",
    "media_asset_id": "m",
    "media_url": (
        "https://example.invalid/"
        "video.mp4"
    ),
    **QUALITY,
    **MEDIA,
}

plan = build_plan([direct])

row = next(
    item
    for item in plan["canaries"]
    if item["account_id"]
    == "night_scout"
    and item["canary_type"]
    == "direct_reference_media"
)

assert (
    row["status"]
    == "READY_FOR_HUMAN_CANARY"
)

pdca = {
    "account_id": "liver_manager",
    "canary_type": "pdca_text",
    "public_post_text": (
        "前回の結果を基に、次の配信では"
        "冒頭の一言を改善します。"
    ),
    "queue_id": "q_pdca",
    "persona_validator_status": "PASS",
    (
        "final_public_post_"
        "validator_status"
    ): "PASS",
    "internal_leak_status": "PASS",
    **{
        **QUALITY,
        "primary_topic": (
            "sustainable_growth"
        ),
    },
}

pdca_plan = build_plan([pdca])

pdca_row = next(
    item
    for item in pdca_plan["canaries"]
    if item["account_id"]
    == "liver_manager"
    and item["canary_type"]
    == "pdca_text"
)

assert (
    pdca_row["status"]
    == "READY_FOR_HUMAN_CANARY"
)

assert (
    plan["would_fetch"] is False
    and plan["would_post"] is False
)

print(
    "PASS "
    "test_bounded_media_canary_plan.py"
)
