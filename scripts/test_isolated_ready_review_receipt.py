#!/usr/bin/env python3
"""Offline concurrency and fail-closed tests for per-invocation READY receipts."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import maintain_text_ready_inventory as maintenance


class IsolatedReadyReviewReceiptTest(unittest.TestCase):
    def test_unique_private_receipts_are_removed_between_calls(self):
        paths = []

        def fake_run(command):
            self.assertEqual(command[-2], "--json-output")
            path = Path(command[-1])
            self.assertTrue(path.parent.is_dir())
            self.assertFalse(path.exists())
            self.assertNotIn("queue_id", str(path))
            paths.append(path)
            path.write_text(json.dumps({"status": "READY", "verified": True}), encoding="utf-8")
            return 0, {"status": "READY"}

        with patch.object(maintenance, "_run", side_effect=fake_run):
            first = maintenance._run_isolated_ready_review(["python", "review.py"])
            second = maintenance._run_isolated_ready_review(["python", "review.py"])

        self.assertEqual(first, (0, {"status": "READY", "verified": True}))
        self.assertEqual(second, first)
        self.assertEqual(len(set(paths)), 2)
        for path in paths:
            self.assertFalse(path.exists())
            self.assertFalse(path.parent.exists())

    def test_malformed_private_receipt_fails_closed_and_is_removed(self):
        paths = []

        def fake_run(command):
            path = Path(command[-1])
            paths.append(path)
            path.write_text("PRIVATE_UNPUBLISHED_TEXT", encoding="utf-8")
            return 0, {"status": "READY"}

        with patch.object(maintenance, "_run", side_effect=fake_run):
            code, result = maintenance._run_isolated_ready_review(["python", "review.py"])
        self.assertEqual(code, 1)
        self.assertEqual(result, {"status": "FAILED", "failure_category": "READY_REVIEW_REPORT_INVALID"})
        self.assertNotIn("PRIVATE_UNPUBLISHED_TEXT", repr(result))
        self.assertFalse(paths[0].exists())

    def test_quota_error_cannot_be_overridden_by_receipt(self):
        def fake_run(command):
            Path(command[-1]).write_text(json.dumps({"status": "READY"}), encoding="utf-8")
            return 1, {"status": "FAILED", "failure_category": "SHEETS_QUOTA_EXHAUSTED"}

        with patch.object(maintenance, "_run", side_effect=fake_run):
            code, result = maintenance._run_isolated_ready_review(["python", "review.py"])
        self.assertEqual(code, 1)
        self.assertEqual(result["failure_category"], "SHEETS_QUOTA_EXHAUSTED")

    def test_missing_receipt_never_inherits_a_previous_file(self):
        with patch.object(maintenance, "_run", return_value=(
            1, {"status": "FAILED", "failure_category": "GENERATION_PROCESS_FAILED"},
        )):
            code, result = maintenance._run_isolated_ready_review(["python", "review.py"])
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
