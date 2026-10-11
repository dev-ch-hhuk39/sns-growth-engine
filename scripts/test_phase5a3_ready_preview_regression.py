#!/usr/bin/env python3
"""Offline regression of bounded read-only previews and Sheets quota fail-closed."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

import run_scheduled_autopost_preview_v2 as preview  # noqa: E402
import maintain_text_ready_inventory as inventory  # noqa: E402


class PreviewScopeTests(unittest.TestCase):
    def test_exact_scopes_and_reject_unknown_slot(self):
        self.assertEqual(len(preview._selected_slots("all", "")), 10)
        self.assertEqual(len(preview._selected_slots("night_scout", "")), 5)
        self.assertEqual(len(preview._selected_slots("liver_manager", "")), 5)
        self.assertEqual(preview._selected_slots("liver_manager", "lm_1800_clip_media"),
                         [("liver_manager", "lm_1800_clip_media", "approved_source_clip")])
        with self.assertRaisesRegex(ValueError, "preview_slot_not_in_account_scope"):
            preview._selected_slots("night_scout", "lm_1800_clip_media")

    def test_checkpoint_contains_only_safe_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "checkpoint.json"
            row = {"account_id": "night_scout", "slot_id": "ns_1400_reference", "status": "BLOCKED",
                   "public_post_text": "PRIVATE_TEXT_NOT_ALLOWED_IN_CHECKPOINT", "source_url": "PRIVATE_SOURCE"}
            with contextlib.redirect_stdout(io.StringIO()):
                preview._checkpoint([row], 1, "", progress_output=str(output))
            text = output.read_text(encoding="utf-8")
            self.assertNotIn("PRIVATE_TEXT", text)
            self.assertNotIn("PRIVATE_SOURCE", text)
            self.assertEqual(json.loads(text)["completed_slots"], 1)
            self.assertFalse((output.with_name(output.name + ".tmp")).exists())

    def test_sheet_read_failure_does_not_become_empty_inventory(self):
        with patch.object(preview, "read_records_safely", side_effect=RuntimeError("SENSITIVE_ERROR")):
            with self.assertRaisesRegex(RuntimeError, "READONLY_SOURCE_READ_FAILED:queue") as caught:
                preview._records(object(), "queue")
        self.assertNotIn("SENSITIVE_ERROR", str(caught.exception))

    def _run_main(self, args, seconds):
        sheet = Mock()
        sheet._readonly_sheet_record_cache = {}
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink), \
             patch.object(preview, "SheetsClient", return_value=sheet), \
             patch.object(preview, "get_config", return_value={"sheet_id": "fixture", "sa_dict": {}}), \
             patch.object(preview, "_records", return_value=[]), \
             patch.object(preview, "_runtime", return_value={"reservations": []}), \
             patch.object(preview, "_activation", return_value={"returncode": 1, "payload": {}}), \
             patch.object(preview, "_text_preview", return_value={
                 "account_id": "night_scout", "slot_id": "ns_1400_reference", "post_type": "reference_text",
                 "status": "PASS", "quality": {"pass": True}, "final_text": "fixture"}) as text_run, \
             patch.object(preview.time, "monotonic", side_effect=seconds), \
             patch.dict(os.environ, {name: "false" for name in preview.REAL_ACTION_FLAGS}):
            result = preview.main(args)
            calls = text_run.call_count
        report_text = sink.getvalue().split("=== SCHEDULED_AUTOPOST_PREVIEW_V2_BEGIN ===")[1].split(
            "=== SCHEDULED_AUTOPOST_PREVIEW_V2_END ===")[0]
        return result, json.loads(report_text), calls

    def test_single_slot_runs_and_reports_only_requested_scope(self):
        result, report, calls = self._run_main(
            ["--account-id", "night_scout", "--slot-id", "ns_1400_reference"], [0.0, 1.0])
        self.assertEqual(result, 0)
        self.assertEqual(calls, 1)
        self.assertEqual(report["slot_count"], 1)
        self.assertEqual(report["slot_status_counts"], {"PASS": 1})
        self.assertTrue(report["queue_unchanged"])
        self.assertFalse(report["writes_performed"])

    def test_deadline_exhaustion_skips_provider_and_is_not_pass(self):
        result, report, calls = self._run_main(
            ["--account-id", "night_scout", "--slot-id", "ns_1400_reference",
             "--deadline-seconds", "300"], [0.0, 290.0])
        self.assertEqual(result, 0)
        self.assertEqual(calls, 0)
        self.assertEqual(report["slot_status_counts"], {"PREVIEW_BUDGET_EXHAUSTED": 1})
        self.assertEqual(report["status"], "PREVIEW_COMPLETE_WITH_BLOCKS")


class SheetsQuotaTests(unittest.TestCase):
    def test_sheets_retry_error_is_classified_without_leaking_details(self):
        completed = SimpleNamespace(returncode=1, stdout="{}",
                                    stderr="[SHEETS_RETRY] open_by_key failed with rate_limit SENSITIVE")
        with patch.object(inventory.subprocess, "run", return_value=completed):
            rc, result = inventory._run(["python3", "fixture.py"])
        self.assertEqual(rc, 1)
        self.assertEqual(result["failure_category"], "SHEETS_QUOTA_EXHAUSTED")
        self.assertNotIn("SENSITIVE", json.dumps(result))

    def test_replenish_stops_retry_chain_when_sheets_quota_exhausted(self):
        slot = {"slot_id": "ns_1400_reference", "business_date_jst": "2026-10-11", "post_type": "reference_text"}
        with patch.object(inventory, "_generation_commands", return_value=[("primary", ["a"]), ("offline", ["b"])]), \
             patch.object(inventory, "_run", return_value=(1, {"status": "FAILED", "failure_category": "SHEETS_QUOTA_EXHAUSTED"})) as runner:
            result = inventory.replenish("night_scout", slot, apply=True)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(result["failure_category"], "SHEETS_QUOTA_EXHAUSTED")
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(result["queue_ids"], [])

    def test_ordinary_generation_failure_retains_bounded_fallback(self):
        slot = {"slot_id": "ns_1400_reference", "business_date_jst": "2026-10-11", "post_type": "reference_text"}
        with patch.object(inventory, "_generation_commands", return_value=[("primary", ["a"]), ("offline", ["b"])]), \
             patch.object(inventory, "_run", return_value=(1, {"status": "FAILED", "failure_category": "GENERATION_PROCESS_FAILED"})) as runner:
            result = inventory.replenish("night_scout", slot, apply=True)
        self.assertEqual(runner.call_count, 2)
        self.assertEqual(result["failure_category"], "GENERATION_PROCESS_FAILED")


if __name__ == "__main__":
    unittest.main()
