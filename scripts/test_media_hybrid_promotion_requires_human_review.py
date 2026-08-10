#!/usr/bin/env python3
"""Only the exact human-approved media row may pass Hybrid promotion."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

import promote_hybrid_approved_media as promotion  # noqa: E402


class FakeClient:
    pass


BASE = {
    "account_id": "night_scout",
    "platform": "threads",
    "slot_id": "ns_1800_direct_media",
    "generation_mode": "direct_reference_media",
    "rights_status": "licensed",
    "permission_status": "approved",
    "validator_status": "PASS",
    "internal_leak_status": "PASS",
    "account_fit_status": "PASS",
    "media_url": "https://res.cloudinary.com/example/video/upload/item.mp4",
}


def plan_for(row: dict[str, str]) -> dict:
    original_reader = promotion.read_records_safely
    original_required = promotion.requires_hybrid_ai_gate
    original_gate = promotion.hybrid_ai_gate_passed
    original_context = promotion.build_source_context
    try:
        promotion.read_records_safely = lambda _client, _logical: [row]
        promotion.requires_hybrid_ai_gate = lambda _row: True
        promotion.hybrid_ai_gate_passed = lambda _row, _context: (True, "pass")
        promotion.build_source_context = lambda _client, _row: {}
        return promotion.build_plan(
            FakeClient(),
            "night_scout",
            "ns_1800_direct_media",
            {str(row["queue_id"])},
        )
    finally:
        promotion.read_records_safely = original_reader
        promotion.requires_hybrid_ai_gate = original_required
        promotion.hybrid_ai_gate_passed = original_gate
        promotion.build_source_context = original_context


unreviewed = plan_for({**BASE, "queue_id": "q_unreviewed", "status": "WAITING_REVIEW"})
assert unreviewed["selected_queue_ids"] == []

ready_without_decision = plan_for({**BASE, "queue_id": "q_ready", "status": "READY"})
assert ready_without_decision["selected_queue_ids"] == []
assert ready_without_decision["rejected"] == [
    {"queue_id": "q_ready", "reasons": "human_review_not_approved"}
]

approved = plan_for({
    **BASE,
    "queue_id": "q_approved",
    "status": "READY",
    "human_review_decision": "OK",
})
assert approved["selected_queue_ids"] == ["q_approved"]

print("PASS test_media_hybrid_promotion_requires_human_review.py")
