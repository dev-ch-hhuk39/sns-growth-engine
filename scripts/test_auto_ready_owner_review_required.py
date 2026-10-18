#!/usr/bin/env python3
"""Owner-review-required must never be disguised as a transient generator error.

Offline-only tests. Nothing is posted, approved, or persisted.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import maintain_text_ready_inventory as maintenance  # noqa: E402


class OwnerReviewReasonTests(unittest.TestCase):
    def test_generator_owner_review_is_sanitized_and_does_not_claim_ready(self):
        raw = {
            "status": "DRAFT_ONLY",
            "reason": "content_quality_v2_owner_review_required",
            "would_post": False,
        }
        result = subprocess.CompletedProcess([], 1, json.dumps(raw), "")
        with patch.object(maintenance.subprocess, "run", return_value=result):
            code, payload = maintenance._run(["no-network"])
        self.assertEqual(code, 1)
        self.assertEqual(payload["status"], "DRAFT_ONLY")
        self.assertEqual(payload["failure_category"], "OWNER_REVIEW_REQUIRED")
        self.assertFalse(payload["would_post"])

    def test_owner_review_is_hard_blocker_but_not_permission_for_auto_ready(self):
        self.assertTrue(maintenance.hard_replenishment_blocker({
            "failure_category": "OWNER_REVIEW_REQUIRED",
        }))
        self.assertTrue(maintenance.hard_replenishment_blocker({
            "attempts": [{"route": "offline_original_bank", "reason": "OWNER_REVIEW_REQUIRED"}],
        }))
        self.assertFalse(maintenance.hard_replenishment_blocker({
            "failure_category": "QUALITY_EXHAUSTED",
        }))

    def test_replenish_does_not_retry_other_routes_after_deliberate_owner_hold(self):
        slot = {"slot_id": "ns_1400_reference",
                "post_type": "reference_text", "business_date_jst": "2026-10-18"}
        rejected = {"status": "DRAFT_ONLY",
                    "reason": "content_quality_v2_owner_review_required",
                    "failure_category": "OWNER_REVIEW_REQUIRED", "would_post": False}
        with patch.object(maintenance, "_run", return_value=(1, rejected)) as run:
            result = maintenance.replenish("night_scout", slot, apply=True)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(result["status"], "OWNER_REVIEW_REQUIRED")
        self.assertEqual(result["failure_category"], "OWNER_REVIEW_REQUIRED")
        self.assertEqual(result["queue_ids"], [])
        self.assertEqual(result["missing"], 1)
        self.assertFalse(result["would_post"])
        self.assertEqual(len(result["attempts"]), 1)

    def test_unknown_provider_errors_remain_distinct(self):
        self.assertEqual(maintenance.generation_failure_category({
            "status": "DRAFT_ONLY", "reason": "not_a_real_reason",
        }), "GENERATION_PROCESS_FAILED")
        self.assertEqual(maintenance.generation_failure_category({
            "status": "QUALITY_EXHAUSTED", "blocked_reasons": ["gemini_rate_limited"],
        }), "PROVIDER_RATE_LIMITED")


if __name__ == "__main__":
    unittest.main()
