#!/usr/bin/env python3
"""Offline tests for isolated scheduled READY result identity and freshness."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_scheduled_text_slot_pipeline as scheduled  # noqa: E402


class ReadyTempfileTests(unittest.TestCase):
    def call(self, payload, *, rc=0, write=True):
        outputs = []

        def fake_stage(name, argv, env):
            self.assertEqual(name, "hybrid_review_and_auto_ready")
            self.assertEqual(argv[argv.index("--queue-id") + 1], "q123")
            path = Path(argv[argv.index("--json-output") + 1])
            outputs.append(path)
            self.assertFalse(path.exists())
            if write:
                path.write_text(
                    payload if isinstance(payload, str) else json.dumps(payload),
                    encoding="utf-8",
                )
            return rc, {"status": "READY", "selected_queue_id": "q123"}

        with patch.object(scheduled, "run_stage", side_effect=fake_stage):
            result = scheduled.run_isolated_hybrid_ready(
                "night_scout", "ns_1600_original", "q123", {},
            )
        for output in outputs:
            self.assertFalse(output.exists())
            self.assertFalse(output.parent.exists())
        return result, outputs

    def test_exact_success_uses_unique_cleaned_tmp_path(self):
        good = {
            "status": "READY", "account_id": "night_scout",
            "slot_id": "ns_1600_original", "selected_queue_id": "q123",
        }
        (first, path1), (second, path2) = self.call(good), self.call(good)
        self.assertEqual(first, (0, good))
        self.assertEqual(second, (0, good))
        self.assertNotEqual(path1[0], path2[0])

    def test_missing_and_corrupt_output_blocks_no_stale_fallback(self):
        result, _ = self.call({}, write=False)
        self.assertEqual(result[0], 2)
        self.assertEqual(result[1]["reason"], "READY_RESULT_NOT_PERSISTED")
        result, _ = self.call("not json")
        self.assertEqual(result[1]["reason"], "READY_RESULT_UNREADABLE")

    def test_forged_account_slot_or_queue_rejected(self):
        base = {"status": "READY", "account_id": "night_scout",
                "slot_id": "ns_1600_original", "selected_queue_id": "q123"}
        for field, value in (
            ("account_id", "liver_manager"),
            ("slot_id", "ns_1400_reference"),
            ("selected_queue_id", "some_other_queue"),
        ):
            payload = {**base, field: value}
            with self.subTest(field=field):
                (rc, saved), _ = self.call(payload)
                self.assertEqual(rc, 2)
                self.assertIn("MISMATCH", saved["reason"])

    def test_no_ready_with_correct_identity_is_recoverable_failure(self):
        payload = {"status": "NO_READY_CANDIDATE", "account_id": "night_scout",
                   "slot_id": "ns_1600_original", "selected_queue_id": ""}
        result, _ = self.call(payload)
        self.assertEqual(result, (0, payload))

    def test_nonzero_exit_remains_failure_even_if_file_claims_ready(self):
        payload = {"status": "READY", "account_id": "night_scout",
                   "slot_id": "ns_1600_original", "selected_queue_id": "q123"}
        result, _ = self.call(payload, rc=2)
        self.assertEqual(result, (2, payload))


if __name__ == "__main__":
    unittest.main()
