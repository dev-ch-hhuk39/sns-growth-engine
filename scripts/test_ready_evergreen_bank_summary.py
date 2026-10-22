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
