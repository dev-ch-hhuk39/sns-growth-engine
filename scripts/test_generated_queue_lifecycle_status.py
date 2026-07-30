#!/usr/bin/env python3
"""Generation quality PASS must never replace queue lifecycle status."""
from create_missing_text_canaries import build_rows
from generate_threads_ideas_from_references import build_fallback_generation_rows
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
print("PASS test_generated_queue_lifecycle_status.py")
