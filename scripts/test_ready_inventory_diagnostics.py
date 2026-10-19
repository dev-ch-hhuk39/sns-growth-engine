#!/usr/bin/env python3
"""Offline tests for account-scoped and redacted READY inventory diagnostics."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ready_inventory_diagnostics as diagnostics


class ReadyInventoryDiagnosticsTests(unittest.TestCase):
    def test_owner_review_is_blocking_and_account_isolated(self):
        data = {"status": "FAILED", "results": [
            {"account_id": "night_scout", "delivery_slo": "FAIL",
             "delivery_generation_failure_category": "OWNER_REVIEW_REQUIRED",
             "delivery_generation_attempts": [{"reason": "OWNER_REVIEW_REQUIRED", "queue_id": "private-id"}]},
            {"account_id": "night_scout", "delivery_slo": "PASS"},
            {"account_id": "liver_manager", "delivery_slo": "FAIL",
             "delivery_generation_failure_category": "SHEETS_QUOTA_EXHAUSTED"},
        ]}
        out = diagnostics.render_report(data, "night_scout")
        self.assertIn("1/2 verified; 1 missing", out)
        self.assertIn("Maintenance outcome: BLOCKED", out)
        self.assertIn("OWNER_REVIEW_REQUIRED: 1", out)
        self.assertNotIn("SHEETS_QUOTA_EXHAUSTED", out)
        self.assertNotIn("private-id", out)

    def test_multiple_causes_count_each_failed_slot_once(self):
        data = {"status": "FAILED", "results": [
            {"account_id": "beauty_account", "delivery_slo": "FAIL",
             "delivery_generation_failure_category": "OWNER_REVIEW_REQUIRED",
             "delivery_generation_attempts": [
                 {"reason": "PROVIDER_CREDENTIALS_MISSING_OR_REJECTED"},
                 {"reason": "PROVIDER_CREDENTIALS_MISSING_OR_REJECTED"}]},
            {"account_id": "beauty_account", "delivery_slo": "FAIL",
             "delivery_generation_failure_category": "PROVIDER_CREDENTIALS_MISSING_OR_REJECTED"},
        ]}
        out = diagnostics.render_report(data, "beauty_account")
        self.assertIn("OWNER_REVIEW_REQUIRED: 1", out)
        self.assertIn("PROVIDER_CREDENTIALS_MISSING_OR_REJECTED: 2", out)

    def test_raw_secret_or_post_text_never_appears(self):
        secret = "ghp_PrivateSecretNotToEcho"
        data = {"status": "FAILED", "results": [
            {"account_id": "night_scout", "delivery_slo": "FAIL",
             "delivery_generation_failure_category": secret,
             "delivery_generation_attempts": [{"reason": secret, "public_post_text": "private caption"}]},
        ]}
        out = diagnostics.render_report(data, "night_scout")
        self.assertIn("UNCLASSIFIED_FAILURE: 1", out)
        self.assertNotIn(secret, out)
        self.assertNotIn("private caption", out)

    def test_empty_report_not_misreported_as_success(self):
        out = diagnostics.render_report({"status": "PASS", "results": []}, "night_scout")
        self.assertIn("Maintenance outcome: BLOCKED", out)
        self.assertIn("NO_REQUIRED_TEXT_SLOTS_OR_REPORT_INCOMPLETE", out)

    def test_generic_failed_slot_is_fail_closed(self):
        out = diagnostics.render_report({"status": "FAILED", "results": [
            {"account_id": "liver_manager", "delivery_slo": "FAIL"}
        ]}, "liver_manager")
        self.assertIn("NO_PUBLISHABLE_READY: 1", out)

    def test_malformed_json_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            path.write_text("{broken", encoding="utf-8")
            with patch("builtins.print") as output:
                code = diagnostics.main(["--account-id", "night_scout", "--report", str(path)])
            self.assertEqual(code, 2)
            self.assertIn("READY_DIAGNOSTICS_UNAVAILABLE", output.call_args.args[0])

    def test_valid_json_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            path.write_text(json.dumps({"status": "FAILED", "results": [
                {"account_id": "night_scout", "delivery_slo": "FAIL",
                 "delivery_generation_failure_category": "OWNER_REVIEW_REQUIRED"}
            ]}), encoding="utf-8")
            with patch("builtins.print") as output:
                code = diagnostics.main(["--account-id", "night_scout", "--report", str(path)])
            self.assertEqual(code, 0)
            self.assertIn("OWNER_REVIEW_REQUIRED", output.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
