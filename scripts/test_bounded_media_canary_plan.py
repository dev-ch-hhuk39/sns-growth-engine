#!/usr/bin/env python3
from build_bounded_media_canary_plan import build_plan

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
    "quality_gate_version": "generation_quality_v3",
}

MEDIA_EVIDENCE = {
    "feature_schema_version": "post_features_v1",
    "media_primary_topic": "work_conditions",
    "visual_topic": "work_conditions",
    "visual_topic_match": True,
    "visual_cta_match": True,
    "visual_plan_version": "visual_plan_v1",
    "visual_text_hash": "visual-hash",
    "claim_support_json": "[{\"verified\": true}]",
}

empty = build_plan([])
assert empty["total_canaries"] == 12
assert all(row["status"] == "PENDING_EVIDENCE" for row in empty["canaries"])
candidate = {
    "account_id": "night_scout", "canary_type": "direct_image", "source_id": "s", "rights_status": "approved_creator_clip",
    "permission_status": "approved", "permission_evidence": "ledger row", "public_post_text": "読者向けの自然な投稿文です。",
    "queue_id": "q", "persona_validator_status": "PASS", "final_public_post_validator_status": "PASS", "internal_leak_status": "PASS", "publisher_media_type": "IMAGE", "alignment_status": "PASS", "final_alignment_score": 1, "main_claim_coverage": 1, "unsupported_claim_count": 0, "source_copy_similarity": 0, "recent_post_similarity": 0, **QUALITY,
    "source_post_id": "p", "media_asset_id": "m", "media_url": "https://example.invalid/image.jpg", **MEDIA_EVIDENCE,
}
plan = build_plan([candidate])
row = next(row for row in plan["canaries"] if row["canary_id"] == "canary_night_scout_direct_image")
assert row["status"] == "READY_FOR_HUMAN_CANARY"
assert plan["would_fetch"] is False and plan["would_post"] is False
text_plan = build_plan([{"account_id": "liver_manager", "canary_type": "original_text", "public_post_text": "配信を始める前に不安を一つずつ整理すると続けやすいです。", "queue_id": "q_text", "persona_validator_status": "PASS", "final_public_post_validator_status": "PASS", "internal_leak_status": "PASS", **{**QUALITY, "primary_topic": "continuity"}}])
assert next(row for row in text_plan["canaries"] if row["canary_id"] == "canary_liver_manager_original_text")["status"] == "READY_FOR_HUMAN_CANARY"
clip_plan = build_plan([{"account_id": "night_scout", "canary_type": "approved_source_clip", "source_id": "s", "rights_status": "owned", "permission_status": "approved", "permission_evidence": "generated", "public_post_text": "読者向けの自然な投稿文です。", "queue_id": "q_clip", "persona_validator_status": "PASS", "final_public_post_validator_status": "PASS", "internal_leak_status": "PASS", "publisher_media_type": "VIDEO", "alignment_status": "PASS", "final_alignment_score": 1, "main_claim_coverage": 1, "unsupported_claim_count": 0, "source_copy_similarity": 0, "recent_post_similarity": 0, **QUALITY, "source_video_id": "v", "clip_candidate_id": "c", "local_path": "/tmp/clip.mp4", "start_seconds": 0, "end_seconds": 8, **MEDIA_EVIDENCE}])
assert next(row for row in clip_plan["canaries"] if row["canary_id"] == "canary_night_scout_approved_source_clip")["status"] == "READY_FOR_HUMAN_CANARY"
print("PASS test_bounded_media_canary_plan.py")
