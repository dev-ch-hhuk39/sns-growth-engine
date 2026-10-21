#!/usr/bin/env python3
"""Safe, synthetic tests: never contact Sheets, Github, Threads or providers."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from summarize_readonly_slot_audit import summarize  # noqa: E402

ACCT = "night_scout"


class AuditSummaryTests(unittest.TestCase):
    def test_pass_keeps_empty_readonly_slots_green(self):
        line, code = summarize({"status": "PASS", "dry_run": True, "results": []}, ACCT)
        self.assertEqual(code, 0)
        self.assertIn("slots=0", line)

    def test_missing_validated_ready_is_actionable_and_still_fails(self):
        row = {"account_id": ACCT, "status": "FAILED",
               "reason": "NO_VALIDATED_BUFFERED_QUEUE",
               "queue_id": "SECRET-QUEUE", "public_post_text": "PRIVATE-TEXT"}
        line, code = summarize({"status": "FAILED", "dry_run": True,
                                "results": [row]}, ACCT)
        self.assertEqual(code, 2)
        self.assertIn("NO_VALIDATED_BUFFERED_QUEUE:1", line)
        self.assertNotIn("SECRET", line)
        self.assertNotIn("PRIVATE", line)

    def test_unknown_reasons_are_never_reflected_into_logs(self):
        x = {"status": "FAILED", "reason": "secret-access-token-XYZ",
             "queue_id": "private", "account_id": ACCT}
        line, code = summarize({"status": "FAILED", "dry_run": True,
                                "results": [x]}, ACCT)
        self.assertEqual(code, 2)
        self.assertIn("OTHER_REDACTED:1", line)
        self.assertNotIn("XYZ", line)

    def test_wrong_account_cannot_be_combined_into_report(self):
        x = {"status": "FAILED", "account_id": "liver_manager",
             "reason": "NO_VALIDATED_BUFFERED_QUEUE"}
        line, code = summarize({"status": "FAILED", "dry_run": True,
                                "results": [x]}, ACCT)
        self.assertEqual(code, 78)
        self.assertIn("ACCOUNT_MISMATCH", line)

    def test_refuses_to_report_apply_results_as_readonly(self):
        _, code = summarize({"status": "PASS", "dry_run": False,
                             "results": []}, ACCT)
        self.assertEqual(code, 78)

    def test_refuses_malformed_or_unbounded_results(self):
        for doc in ([], {"status": "PASS", "dry_run": True},
                    {"status": "PASS", "dry_run": True,
                     "results": [{} for _ in range(101)]}):
            self.assertEqual(summarize(doc, ACCT)[1], 78)

    def test_cli_exit_and_no_private_values_in_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slot-audit.json"
            path.write_text(json.dumps({
                "status": "FAILED", "dry_run": True,
                "results": [{
                    "account_id": ACCT,
                    "status": "BLOCKED",
                    "reason": "provider-private-message-bearer-xyz",
                    "public_post_text": "DO-NOT-LOG-TEXT",
                }],
            }), encoding="utf-8")
            completed = subprocess.run([
                sys.executable,
                str(ROOT / "scripts/summarize_readonly_slot_audit.py"),
                "--report-file", str(path), "--account-id", ACCT,
            ], capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("OTHER_REDACTED:1", completed.stdout)
            self.assertNotIn("DO-NOT-LOG", completed.stdout + completed.stderr)
            self.assertNotIn("bearer", completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
