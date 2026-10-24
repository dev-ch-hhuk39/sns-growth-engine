#!/usr/bin/env python3
"""Public CI logging never contains unpublished evergreen queue details."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ready_evergreen_bank_summary as mod


class SafeBankSummaryTest(unittest.TestCase):
    @staticmethod
    def report():
        return {
            "mode": "EVERGREEN_BANK", "status": "PASS", "would_post": False,
            "evergreen_bank_by_account": {
                "night_scout": {
                    "status": "READY_INVENTORY_OK", "usable_evergreen": 5, "minimum": 3
                },
            },
            "results": [
                {"account_id": "night_scout", "attempts": [
                    {"queue_id": "SECRET_PRIVATE_QUEUE_ID",
                     "public_post_text": "SECRET_PRIVATE_CAPTION"}]},
            ],
        }

    def test_valid_fixed_fields_no_content(self):
        receipt, ok = mod.redacted_bank_summary(self.report(), "night_scout")
        self.assertTrue(ok)
        self.assertIn("status=PASS", receipt)
        self.assertIn("usable=5 minimum=3", receipt)
        self.assertNotIn("SECRET", receipt)

    def test_failure_does_not_surface_malicious_reason(self):
        data = self.report()
        data["status"] = "SECRET_PRIVATE_PROVIDER_OUTPUT"
        receipt, ok = mod.redacted_bank_summary(data, "night_scout")
        self.assertFalse(ok)
        self.assertNotIn("SECRET", receipt)

    def test_account_boundary_fails_closed(self):
        data = self.report()
        data["evergreen_bank_by_account"]["liver_manager"] = {}
        receipt, ok = mod.redacted_bank_summary(data, "night_scout")
        self.assertFalse(ok)
        self.assertIn("INCOMPLETE_ACCOUNT_SCOPE", receipt)

    def test_malformed_counts_fail_closed(self):
        data = self.report()
        data["evergreen_bank_by_account"]["night_scout"]["usable_evergreen"] = "SECRET_PRIVATE"
        receipt, ok = mod.redacted_bank_summary(data, "night_scout")
        self.assertFalse(ok)
        self.assertEqual(receipt.split("status=")[-1], "INVALID_COUNTS")

    def test_failed_bank_outputs_bounded_shortfall_and_whitelisted_cause(self):
        r = self.report()
        r["status"] = "FAILED"
        r["evergreen_bank_by_account"]["night_scout"].update(
            status="QUALITY_EXHAUSTED", usable_evergreen=2, minimum=10)
        r["results"] = [{"account_id": "night_scout", "attempts": [
            {"failure_category": "AI_APPROVAL_BUDGET_EXHAUSTED",
             "public_post_text": "PRIVATE_DRAFT_MUST_NOT_LEAK"},
        ]}]
        receipt, okay = mod.redacted_bank_summary(r, "night_scout")
        self.assertFalse(okay)
        self.assertIn("usable=2 minimum=10", receipt)
        self.assertIn("category=AI_APPROVAL_BUDGET_EXHAUSTED", receipt)
        self.assertNotIn("PRIVATE_DRAFT", receipt)

    def test_unknown_provider_text_never_appears(self):
        r = self.report()
        r["status"] = "FAILED"
        r["evergreen_bank_by_account"]["night_scout"].update(
            status="QUALITY_EXHAUSTED", usable_evergreen=0, minimum=10)
        r["results"] = [{"account_id": "night_scout", "attempts": [
            {"failure_category": "SECRET_TOKEN_UNPUBLISHED_QUEUE_ID"}
        ]}]
        receipt, okay = mod.redacted_bank_summary(r, "night_scout")
        self.assertFalse(okay)
        self.assertIn("category=UNCLASSIFIED", receipt)
        self.assertNotIn("SECRET_TOKEN", receipt)

    def test_missing_json_with_private_stderr_classified_not_leaked(self):
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "report.json"
            err = Path(root) / "stderr"
            out.write_text("PRIVATE_UNPUBLISHED_CAPTION", encoding="utf-8")
            err.write_text("ReadTimeout token=PRIVATE_SESSION_KEY", encoding="utf-8")
            target = io.StringIO()
            with patch.object(sys, "argv", [
                "summary", "--account-id", "night_scout",
                "--report", str(out), "--private-stderr", str(err),
            ]), contextlib.redirect_stdout(target):
                code = mod.main()
            self.assertEqual(code, 2)
            self.assertIn("PRIVATE_FAILURE_HINT=PROCESS_TIMEOUT", target.getvalue())
            self.assertNotIn("PRIVATE_SESSION_KEY", target.getvalue())
            self.assertNotIn("PRIVATE_UNPUBLISHED_CAPTION", target.getvalue())

    def test_private_input_file_never_printed_by_cli(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "report.json"
            path.write_text(json.dumps(self.report()), encoding="utf-8")
            output = io.StringIO()
            with patch.object(sys, "argv",
                              ["summary", "--account-id", "night_scout",
                               "--report", str(path)]), contextlib.redirect_stdout(output):
                code = mod.main()
            self.assertEqual(code, 0)
            self.assertNotIn("SECRET_PRIVATE", output.getvalue())

    def test_final_scoped_report_survives_bounded_prior_stdout(self):
        report = self.report()
        raw = 'synthetic progress\n{"status":"UNRELATED"}\n'
        raw += json.dumps(report, ensure_ascii=False, indent=2)
        parsed = mod.parse_bounded_bank_json(raw, "night_scout")
        receipt, ok = mod.redacted_bank_summary(parsed, "night_scout")
        self.assertTrue(ok)
        self.assertIn("usable=5", receipt)
        self.assertNotIn("UNRELATED", receipt)

    def test_trailing_text_or_fake_final_object_never_falls_back_to_old_pass(self):
        valid = json.dumps(self.report())
        for suffix in ("\nBAD_TRAILING_OUTPUT", '\n{"mode":"EVERGREEN_BANK","status":"FAILED"}'):
            with self.subTest(suffix=suffix):
                with self.assertRaises(ValueError):
                    mod.parse_bounded_bank_json(valid + suffix, "night_scout")

    def test_missing_guard_or_foreign_account_fails_closed(self):
        report = self.report()
        report["would_post"] = True
        with self.assertRaises(ValueError):
            mod.parse_bounded_bank_json(json.dumps(report), "night_scout")
        report["would_post"] = False
        with self.assertRaises(ValueError):
            mod.parse_bounded_bank_json(json.dumps(report), "beauty_account")
        with self.assertRaises(ValueError):
            mod.parse_bounded_bank_json("{}", "night_scout")

    def test_bounded_account_scoped_readback_rejections_without_private_data(self):
        report = self.report()
        report["status"] = "FAILED"
        report["evergreen_bank_by_account"]["night_scout"].update(
            status="QUALITY_EXHAUSTED", usable_evergreen=29, minimum=30)
        report["results"] = [
            {"account_id": "night_scout", "attempts": [
                {"failure_category": "GENERATED_READBACK_UNVERIFIED",
                 "queue_id": "PRIVATE_QUEUE_123",
                 "verification_rejection_counts": {
                     "GENERATED_NOT_READY": 2,
                     "GENERATED_READBACK_UNVERIFIED": 1,
                     "PRIVATE_CAPTION_SHOULD_NOT_PRINT": 3,
                     "GENERATED_IDENTITY_MISMATCH": "SECRET_PROVIDER_MESSAGE",
                     "GENERATED_APPROVAL_INCOMPLETE": 99,
                 }},
            ]},
            {"account_id": "beauty_account", "attempts": [
                {"verification_rejection_counts": {"GENERATED_RUNTIME_GATE_REJECTED": 2}},
            ]},
        ]
        receipt, ok = mod.redacted_bank_summary(report, "night_scout")
        self.assertFalse(ok)
        self.assertIn("usable=29 minimum=30", receipt)
        self.assertIn("category=GENERATED_READBACK_UNVERIFIED", receipt)
        self.assertIn("GENERATED_NOT_READY:2", receipt)
        self.assertIn("GENERATED_READBACK_UNVERIFIED:1", receipt)
        for forbidden in (
            "PRIVATE_QUEUE", "PRIVATE_CAPTION", "SECRET_PROVIDER_MESSAGE",
            "GENERATED_RUNTIME_GATE_REJECTED", "GENERATED_APPROVAL_INCOMPLETE:99",
        ):
            self.assertNotIn(forbidden, receipt)

    def test_untrusted_rejection_map_never_surfaces_freeform_text(self):
        report = self.report()
        report["status"] = "FAILED"
        report["evergreen_bank_by_account"]["night_scout"].update(
            status="QUALITY_EXHAUSTED", usable_evergreen=0, minimum=30)
        report["results"] = [{"account_id": "night_scout", "attempts": [
            {"verification_rejection_counts": {
                "SECRET_PRIVATE_TOKEN": 1, "GENERATED_NOT_READY": True,
            }},
            {"verification_rejection_counts": "PRIVATE_FREEFORM_TEXT"},
        ]}]
        receipt, ok = mod.redacted_bank_summary(report, "night_scout")
        self.assertFalse(ok)
        self.assertNotIn("SECRET_PRIVATE_TOKEN", receipt)
        self.assertNotIn("PRIVATE_FREEFORM_TEXT", receipt)
        self.assertNotIn("GENERATED_NOT_READY:True", receipt)
        self.assertNotIn("readback_rejections=", receipt)

    def test_missing_file_gives_only_fixed_error(self):
        output = io.StringIO()
        with patch.object(sys, "argv",
                          ["summary", "--account-id", "night_scout",
                           "--report", "/tmp/nonexistent-ready-summary-file-expected"]), \
                contextlib.redirect_stdout(output):
            code = mod.main()
        self.assertEqual(code, 2)
        self.assertEqual(output.getvalue().strip(), "EVERGREEN_BANK_REDACTED: status=UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
