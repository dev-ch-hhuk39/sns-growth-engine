#!/usr/bin/env python3
"""Offline fail-closed identity and concurrency tests for hybrid READY receipts."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import maintain_text_ready_inventory as maintenance


COMMAND = [
    "python", "review.py", "--account-id", "night_scout",
    "--slot-id", "ns_1400_reference", "--queue-id", "q_synthetic",
]


def valid_receipt(status="READY"):
    return {
        "status": status,
        "account_id": "night_scout",
        "slot_id": "ns_1400_reference",
        "selected_queue_id": "q_synthetic" if status == "READY" else "",
        "would_post": False,
    }


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
            path.write_text(json.dumps(valid_receipt()), encoding="utf-8")
            return 0, {"status": "READY"}

        with patch.object(maintenance, "_run", side_effect=fake_run):
            first = maintenance._run_isolated_ready_review(COMMAND)
            second = maintenance._run_isolated_ready_review(COMMAND)

        self.assertEqual(first, (0, valid_receipt()))
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
            code, result = maintenance._run_isolated_ready_review(COMMAND)
        self.assertEqual(code, 2)
        self.assertEqual(result, {
            "status": "FAILED", "failure_category": "READY_REVIEW_REPORT_INVALID",
        })
        self.assertNotIn("PRIVATE_UNPUBLISHED_TEXT", repr(result))
        self.assertFalse(paths[0].exists())

    def test_quota_error_cannot_be_overridden_by_receipt(self):
        def fake_run(command):
            Path(command[-1]).write_text(json.dumps(valid_receipt()), encoding="utf-8")
            return 1, {"status": "FAILED", "failure_category": "SHEETS_QUOTA_EXHAUSTED"}

        with patch.object(maintenance, "_run", side_effect=fake_run):
            code, result = maintenance._run_isolated_ready_review(COMMAND)
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure_category"], "SHEETS_QUOTA_EXHAUSTED")

    def test_missing_receipt_does_not_trust_stdout_success(self):
        with patch.object(maintenance, "_run", return_value=(0, valid_receipt())):
            code, result = maintenance._run_isolated_ready_review(COMMAND)
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure_category"], "READY_REVIEW_REPORT_INVALID")

    def test_missing_receipt_preserves_an_actual_subprocess_error(self):
        with patch.object(maintenance, "_run", return_value=(
            124, {"status": "FAILED", "failure_category": "GENERATION_PROCESS_TIMEOUT"},
        )):
            code, result = maintenance._run_isolated_ready_review(COMMAND)
        self.assertEqual(code, 124)
        self.assertEqual(result["failure_category"], "GENERATION_PROCESS_TIMEOUT")

    def test_wrong_account_slot_queue_and_no_post_guard_rejected(self):
        for field, value in (
            ("account_id", "beauty_account"),
            ("slot_id", "ns_1600_original"),
            ("selected_queue_id", "q_other"),
            ("selected_queue_id", None),
            ("would_post", True),
            ("would_post", None),
        ):
            with self.subTest(field=field, value=value):
                def fake_run(command):
                    data = {**valid_receipt(), field: value}
                    Path(command[-1]).write_text(json.dumps(data), encoding="utf-8")
                    return 0, data
                with patch.object(maintenance, "_run", side_effect=fake_run):
                    code, result = maintenance._run_isolated_ready_review(COMMAND)
                self.assertEqual(code, 2)
                self.assertEqual(result, {
                    "status": "FAILED", "failure_category": "READY_REVIEW_REPORT_INVALID",
                })

    def test_non_ready_receipt_stays_no_candidate(self):
        def fake_run(command):
            data = valid_receipt("NO_READY_CANDIDATE")
            Path(command[-1]).write_text(json.dumps(data), encoding="utf-8")
            return 0, data

        with patch.object(maintenance, "_run", side_effect=fake_run):
            code, result = maintenance._run_isolated_ready_review(COMMAND)
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "NO_READY_CANDIDATE")

    def test_invalid_command_does_not_run_provider(self):
        with patch.object(maintenance, "_run") as run:
            code, result = maintenance._run_isolated_ready_review(
                ["python", "review.py", "--json-output", "/tmp/someone-elses-result"]
            )
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "FAILED")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
