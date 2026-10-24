#!/usr/bin/env python3
"""No-network regression for bounded paid READY generation retries.

This file never invokes an API, Google Sheets, paid AI or real SNS posting.
"""
from __future__ import annotations

import sys
import json
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import maintain_text_ready_inventory as maintenance  # noqa: E402

SLOT = {
    "slot_id": "ns_1400_reference",
    "post_type": "reference_text",
    "business_date_jst": "2026-10-22",
}
ROUTES = [
    ("primary", ["paid-primary"]),
    ("safe_original_fallback", ["paid-fallback"]),
    ("offline_original_bank", ["offline"]),
]


def simulate(first_category, offline_category="QUALITY_EXHAUSTED"):
    calls = []
    def run(command):
        calls.append(command[0])
        if command[0] == "paid-primary":
            return 1, {"status": "FAILED", "failure_category": first_category}
        if command[0] == "paid-fallback":
            raise AssertionError("paid retry must have been stopped")
        return 1, {"status": "QUALITY_EXHAUSTED", "failure_category": offline_category}
    with patch.object(maintenance, "_generation_commands", return_value=ROUTES), \
         patch.object(maintenance, "_run", side_effect=run):
        result = maintenance.replenish("night_scout", SLOT, apply=True)
    return calls, result


class PaidRetryContainmentTests(unittest.TestCase):
    def test_provider_budget_exhaustion_skips_further_paid_generation(self):
        calls, result = simulate("AI_APPROVAL_BUDGET_EXHAUSTED")
        self.assertEqual(calls, ["paid-primary", "offline"])
        self.assertEqual(result["failure_category"], "AI_APPROVAL_BUDGET_EXHAUSTED")
        self.assertEqual(result["status"], "QUALITY_EXHAUSTED")
        self.assertFalse(result["would_post"])

    def test_process_timeout_skips_further_paid_generation(self):
        calls, result = simulate("GENERATION_PROCESS_TIMEOUT")
        self.assertEqual(calls, ["paid-primary", "offline"])
        self.assertEqual(result["failure_category"], "GENERATION_PROCESS_TIMEOUT")

    def test_provider_rate_limit_skips_further_paid_generation(self):
        calls, result = simulate("PROVIDER_RATE_LIMITED")
        self.assertEqual(calls, ["paid-primary", "offline"])
        self.assertEqual(result["failure_category"], "PROVIDER_RATE_LIMITED")

    def test_provider_configuration_error_skips_further_paid_generation(self):
        calls, result = simulate("PROVIDER_CONFIGURATION_ERROR")
        self.assertEqual(calls, ["paid-primary", "offline"])
        self.assertEqual(result["failure_category"], "PROVIDER_CONFIGURATION_ERROR")

    def test_nested_approval_runtime_errors_stop_another_paid_generation(self):
        calls = []
        def run(command):
            calls.append(command[0])
            if command[0] == "paid-primary":
                return 1, {"runtime_errors": [
                    {"reason": "HYBRID_AI_DAILY_LIMIT_EXCEEDED"}
                ]}
            if command[0] == "paid-fallback":
                raise AssertionError("unexpected paid retry")
            return 1, {"status": "QUALITY_EXHAUSTED"}
        with patch.object(maintenance, "_generation_commands", return_value=ROUTES), \
             patch.object(maintenance, "_run", side_effect=run):
            result = maintenance.replenish("night_scout", SLOT, apply=True)
        self.assertEqual(calls, ["paid-primary", "offline"])
        self.assertEqual(result["failure_category"], "AI_APPROVAL_BUDGET_EXHAUSTED")

    def test_valid_offline_candidate_keeps_original_owner_and_ai_gates(self):
        calls = []
        def run(command):
            calls.append(command[0])
            if command[0] == "paid-primary":
                return 1, {"failure_category": "AI_APPROVAL_BUDGET_EXHAUSTED"}
            if command[0] == "offline":
                return 0, {"queue_ids": ["synthetic-q1"]}
            self.assertIn("scripts/run_hybrid_ready_pipeline.py", command)
            self.assertIn("--autonomous-low-risk", command)
            self.assertEqual(command[-2], "--json-output")
            Path(command[-1]).write_text(json.dumps({
                "status": "READY", "account_id": "night_scout",
                "slot_id": SLOT["slot_id"], "selected_queue_id": "synthetic-q1",
                "would_post": False,
            }), encoding="utf-8")
            return 0, {"status": "READY"}
        with patch.object(maintenance, "_generation_commands", return_value=ROUTES), \
             patch.object(maintenance, "_run", side_effect=run):
            result = maintenance.replenish("night_scout", SLOT, apply=True)
        self.assertEqual(calls, ["paid-primary", "offline", sys.executable])
        self.assertEqual(result["status"], "READY_REPLENISHED")
        self.assertEqual(result["generation_route"], "offline_original_bank")
        self.assertEqual(result["queue_ids"], ["synthetic-q1"])
        self.assertFalse(result["would_post"])

    def test_original_quality_failure_keeps_existing_safe_paid_fallback(self):
        calls = []
        def run(command):
            calls.append(command[0])
            if command[0] == "paid-primary":
                return 1, {"failure_category": "QUALITY_EXHAUSTED"}
            if command[0] == "paid-fallback":
                return 0, {"queue_ids": ["synthetic-q2"]}
            self.assertIn("--autonomous-low-risk", command)
            self.assertEqual(command[-2], "--json-output")
            Path(command[-1]).write_text(json.dumps({
                "status": "READY", "account_id": "night_scout",
                "slot_id": SLOT["slot_id"], "selected_queue_id": "synthetic-q2",
                "would_post": False,
            }), encoding="utf-8")
            return 0, {"status": "READY"}
        with patch.object(maintenance, "_generation_commands", return_value=ROUTES), \
             patch.object(maintenance, "_run", side_effect=run):
            result = maintenance.replenish("night_scout", SLOT, apply=True)
        self.assertEqual(calls, ["paid-primary", "paid-fallback", sys.executable])
        self.assertEqual(result["status"], "READY_REPLENISHED")
        self.assertFalse(result["would_post"])

    def test_owner_review_required_is_still_a_hard_stop(self):
        calls = []
        def run(command):
            calls.append(command[0])
            return 1, {"failure_category": "OWNER_REVIEW_REQUIRED"}
        with patch.object(maintenance, "_generation_commands", return_value=ROUTES), \
             patch.object(maintenance, "_run", side_effect=run):
            result = maintenance.replenish("night_scout", SLOT, apply=True)
        self.assertEqual(calls, ["paid-primary"])
        self.assertEqual(result["status"], "OWNER_REVIEW_REQUIRED")

    def test_sheets_quota_exhaustion_stops_all_routes(self):
        calls = []
        def run(command):
            calls.append(command[0])
            return 1, {"failure_category": "SHEETS_QUOTA_EXHAUSTED"}
        with patch.object(maintenance, "_generation_commands", return_value=ROUTES), \
             patch.object(maintenance, "_run", side_effect=run):
            result = maintenance.replenish("night_scout", SLOT, apply=True)
        self.assertEqual(calls, ["paid-primary"])
        self.assertEqual(result["failure_category"], "SHEETS_QUOTA_EXHAUSTED")


if __name__ == "__main__":
    unittest.main()
