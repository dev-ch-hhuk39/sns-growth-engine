#!/usr/bin/env python3
"""Generation quality PASS must never replace queue lifecycle status."""
from create_missing_text_canaries import build_rows
from generate_threads_ideas_from_references import _feature_fields, _reference_quality, build_fallback_generation_rows
from generation_quality_gates import persisted_quality_evidence

quality = {"status": "PASS", "batch_diversity_status": "PASS"}
evidence = persisted_quality_evidence(quality)
assert "status" not in evidence
assert evidence["batch_diversity_status"] == "PASS"

text = build_rows([], [], batch_id="queue_status_contract")
assert text["status"] == "PLAN_ONLY", text
assert len(text["rows"]) == 4, text
assert all(row["status"] == "WAITING_REVIEW" for row in text["rows"]), text
assert all(row["batch_diversity_status"] == "PASS" for row in text["rows"]), text

scheduled = build_fallback_generation_rows(
    account_id="liver_manager",
    top_n=1,
    slot_id="lm_status_contract",
    post_type="original_text",
    schedule_date_jst="2026-07-30",
)
assert len(scheduled["queue"]) == 1, scheduled
row = scheduled["queue"][0]
assert row["status"] == "WAITING_REVIEW", row
assert row["content_type"] == "original_text", row
assert row["quality_gate_version"] == "generation_quality_v3", row

reference_quality = _reference_quality(
    "liver_manager",
    "配信の最後に次回の時間を一つ伝えると、初見さんも戻る予定を立てやすいよ。",
    [],
    batch_compared=[],
    structure_variant="1",
)
reference_fields = _feature_fields(
    {
        "feature_schema_version": "post_features_v1",
        "post_design": {"hook_text": "配信の最後", "closing_text": "伝えてみてね"},
    },
    reference_quality,
)
assert reference_fields["feature_schema_version"] == "post_features_v1", reference_fields
assert reference_fields["quality_gate_version"] == "generation_quality_v3", reference_fields
print("PASS test_generated_queue_lifecycle_status.py")
