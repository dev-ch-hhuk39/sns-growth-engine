#!/usr/bin/env python3
"""Offline regression: hosted aftercare logs never expose row-level evidence."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from run_growth_attribution_cycle import (public_growth_cycle_report,
                                          growth_cycle_exit_code,
                                          empty_attribution_observation_state)

ROOT = Path(__file__).resolve().parents[1]


class GrowthAttributionLogTests(unittest.TestCase):
    def test_public_report_includes_status_and_counts_only(self):
        raw = {
            "status": "OUTCOME_UNKNOWN_BLOCKED",
            "account_id": "night_scout",
            "observation_count": 14,
            "attribution_count": 14,
            "strategy_row_count": 23,
            "active_strategy_count": 10,
            "would_write": False,
            "would_post": False,
            "reason": "attribution_external_outcome_unknown",
            "external_write_outcome_uncertain": True,
            "external_write_may_have_occurred": True,
            "requires_readonly_reconciliation": True,
            "attributions": [{"result_id": "PRIVATE_RESULT_123",
                              "metric_evidence_json": "PRIVATE_METRIC_456"}],
            "strategy_state": [{"strategy_id": "PRIVATE_STRATEGY_789"}],
            "provider_response": "PRIVATE_RESPONSE",
            "errors": [{"text": "PRIVATE_ERROR"}],
        }
        safe = public_growth_cycle_report(raw)
        rendered = json.dumps(safe)
        for secret in ("PRIVATE_RESULT_123", "PRIVATE_METRIC_456",
                       "PRIVATE_STRATEGY_789", "PRIVATE_RESPONSE", "PRIVATE_ERROR"):
            self.assertNotIn(secret, rendered)
        self.assertEqual(safe["status"], "OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(safe["observation_count"], 14)
        self.assertTrue(safe["requires_readonly_reconciliation"])
        self.assertTrue(safe["external_write_outcome_uncertain"])

    def test_unapproved_nested_fields_and_non_scalar_values_filtered(self):
        raw = {
            "status": {"not": "a string"},
            "account_id": ["secret-account"],
            "reason": ["secret free text"],
            "would_post": False,
            "would_write": False,
            "attribution_count": 0,
            "unsafe_token": "SECRET_TOKEN_NEVER_LOG",
        }
        safe = public_growth_cycle_report(raw)
        self.assertEqual(safe, {"would_post": False, "would_write": False,
                                "attribution_count": 0})

    def test_plan_status_is_preserved_without_external_rows(self):
        safe = public_growth_cycle_report({
            "status": "PLAN_ONLY", "account_id": "beauty_account",
            "observation_count": 0, "attribution_count": 0,
            "attributions": [], "strategy_state": [], "would_post": False,
        })
        self.assertEqual(safe["status"], "PLAN_ONLY")
        self.assertEqual(safe["observation_count"], 0)
        self.assertNotIn("attributions", safe)
        self.assertNotIn("strategy_state", safe)

    def test_verified_no_data_is_successful_noop_without_misleading_results(self):
        missing = {
            "status": "NO_MEASURED_OBSERVATIONS",
            "account_id": "beauty_account",
            "observation_count": 0,
            "reason": "no_verified_metrics_for_account",
            "would_write": False,
            "would_post": False,
            "attributions": [],
            "strategy_state": [],
        }
        self.assertEqual(growth_cycle_exit_code(missing), 0)
        safe = public_growth_cycle_report(missing)
        self.assertEqual(safe["status"], "NO_MEASURED_OBSERVATIONS")
        self.assertFalse(safe["would_write"])
        self.assertFalse(safe["would_post"])
        self.assertNotIn("attributions", safe)
        self.assertNotIn("strategy_state", safe)

    def test_zero_metrics_never_hides_blocked_or_unknown_writes(self):
        for payload in (
            {"status": "NO_MEASURED_OBSERVATIONS", "observation_count": 1,
             "would_write": False},
            {"status": "NO_MEASURED_OBSERVATIONS", "observation_count": 0,
             "would_write": True},
            {"status": "NO_MEASURED_OBSERVATIONS", "observation_count": 0,
             "would_write": False, "external_write_outcome_uncertain": True},
            {"status": "READ_FAILED", "would_write": False},
            {"status": "OUTCOME_UNKNOWN_BLOCKED", "would_write": False},
            {"status": "BLOCKED", "would_write": False},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(growth_cycle_exit_code(payload), 1)
        self.assertEqual(growth_cycle_exit_code({"status": "APPLIED"}), 0)

    def test_beauty_historical_measured_posts_without_features_not_called_no_metrics(self):
        posted = [{"account_id": "beauty_account", "status": "POSTED",
                   "feature_schema_version": "", "result_id": "historical_1"}]
        snap = [{"account_id": "beauty_account", "result_id": "historical_1",
                 "metrics_status": "MEASURED"}]
        reason = empty_attribution_observation_state(
            posted, snap, account_id="beauty_account")
        self.assertEqual(reason, {
            "status": "NO_ELIGIBLE_ATTRIBUTION_OBSERVATIONS",
            "reason": "measured_posts_missing_feature_provenance",
        })
        self.assertEqual(growth_cycle_exit_code({
            **reason, "observation_count": 0, "would_write": False,
        }), 0)

    def test_empty_feature_metric_join_diagnoses_without_fabrication(self):
        posted = [{"account_id": "liver_manager", "status": "POSTED",
                   "feature_schema_version": "post_features_v1", "result_id": "post"}]
        snap = [{"account_id": "liver_manager", "result_id": "elsewhere",
                 "metrics_status": "MEASURED"}]
        self.assertEqual(
            empty_attribution_observation_state(
                posted, snap, account_id="liver_manager")["reason"],
            "measured_snapshots_no_eligible_feature_join",
        )
        self.assertEqual(
            empty_attribution_observation_state(
                posted, snap, account_id="night_scout")["status"],
            "NO_MEASURED_OBSERVATIONS",
        )

    def test_no_measured_workflow_remains_visible_to_operator(self):
        workflow = (ROOT / ".github/workflows/production-autopilot-aftercare.yml").read_text()
        self.assertIn("growth_attribution_status=NO_ELIGIBLE_OR_NO_MEASURED_OBSERVATIONS", workflow)
        self.assertIn("NO_ELIGIBLE_ATTRIBUTION_OBSERVATIONS", workflow)
        self.assertIn("::warning::No eligible feature attribution", workflow)

    def test_sheets_stdout_uses_public_result_and_keeps_local_explicit_output(self):
        source = (ROOT / "scripts" / "run_growth_attribution_cycle.py").read_text()
        self.assertIn("public_growth_cycle_report(result) if args.use_sheets else result", source)
        self.assertIn('Path(args.output).write_text(json.dumps(result', source)
        self.assertIn("return growth_cycle_exit_code(result)", source)


if __name__ == "__main__":
    unittest.main()
