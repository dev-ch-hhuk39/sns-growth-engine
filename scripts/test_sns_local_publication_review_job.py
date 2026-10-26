#!/usr/bin/env python3
"""No-network tests of publication review write safety and fail-closed gate."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import sns_local_publication_review_job as job


def result(args, report, code=0):
    return subprocess.CompletedProcess(args, code, json.dumps(report), "PRIVATE_SHEETS_SECRET")


SYNC = {"status": "APPLIED", "review_count": 4, "appended_count": 1,
        "updated_count": 0, "unchanged_review_rows": 3, "read_after_write": True}
DECISIONS = {"status": "APPLIED", "decision_count": 1,
             "queue_read_after_write": True, "review_read_after_write": True,
             "updated_queue_ids": ["SENSITIVE_ID"]}


class ReviewJobTests(unittest.TestCase):
    def test_two_stages_no_publish_and_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(job.subprocess, "run", side_effect=[
                result([], SYNC), result([], DECISIONS),
            ]) as called:
                status, summary = job.run(base=Path(tmp), state_dir=Path(tmp))
            self.assertEqual(status, "PASS")
            self.assertEqual(summary["decisions"], {"decision_count": 1})
            self.assertNotIn("SENSITIVE_ID", str(summary))
            self.assertEqual(called.call_count, 2)
            for invocation in called.call_args_list:
                args = invocation.args[0]
                kwargs = invocation.kwargs
                self.assertIn("--apply", args)
                self.assertEqual(kwargs["env"]["PUBLISH_ENABLED"], "false")
                self.assertEqual(kwargs["env"]["ALLOW_REAL_THREADS_POST"], "false")

    def test_readback_missing_latches_and_never_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            malformed = {**SYNC, "read_after_write": False}
            with patch.object(job.subprocess, "run", return_value=result([], malformed)) as call:
                with self.assertRaisesRegex(job.ReviewJobBlocked, "REVIEW_MANUAL"):
                    job.run(base=Path(tmp), state_dir=Path(tmp))
                self.assertEqual(call.call_count, 1)
            self.assertTrue((Path(tmp) / job.LATCH).exists())
            with patch.object(job.subprocess, "run") as call:
                with self.assertRaisesRegex(job.ReviewJobBlocked, "REVIEW_MANUAL"):
                    job.run(base=Path(tmp), state_dir=Path(tmp))
                call.assert_not_called()

    def test_provider_error_latches_and_redacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(job.subprocess, "run", side_effect=RuntimeError("PRIVATE_TOKEN")):
                with self.assertRaisesRegex(job.ReviewJobBlocked, "REVIEW_MANUAL"):
                    job.run(base=Path(tmp), state_dir=Path(tmp))
            self.assertNotIn("PRIVATE_TOKEN", (Path(tmp) / job.LATCH).read_text())

    def test_process_termination_during_write_still_latches(self):
        class Crash(BaseException):
            pass
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / job.LATCH
            def crash(*args, **kwargs):
                self.assertTrue(marker.exists())
                raise Crash()
            with patch.object(job.subprocess, "run", side_effect=crash):
                with self.assertRaises(Crash):
                    job.run(base=Path(tmp), state_dir=Path(tmp))
            before = marker.read_bytes()
            with patch.object(job.subprocess, "run") as process:
                with self.assertRaises(job.ReviewJobBlocked):
                    job.run(base=Path(tmp), state_dir=Path(tmp))
                process.assert_not_called()
            self.assertEqual(before, marker.read_bytes())

    def test_intent_persistence_failure_prevents_child_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(job, "sync_state_directory", side_effect=OSError("private")), \
                    patch.object(job.subprocess, "run") as process:
                with self.assertRaises(job.ReviewJobBlocked):
                    job.run(base=Path(tmp), state_dir=Path(tmp))
                process.assert_not_called()
            self.assertTrue((Path(tmp) / job.LATCH).exists())

    def test_legacy_quarantine_is_not_auto_cleared_even_with_successful_fixtures(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / job.LATCH
            marker.write_text("LEGACY_UNKNOWN_WRITE")
            with patch.object(job.subprocess, "run", side_effect=[result([], SYNC), result([], DECISIONS)]) as process:
                with self.assertRaises(job.ReviewJobBlocked):
                    job.run(base=Path(tmp), state_dir=Path(tmp))
                process.assert_not_called()
            self.assertEqual(marker.read_text(), "LEGACY_UNKNOWN_WRITE")

    def test_verified_pair_completes_only_own_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(job.subprocess, "run", side_effect=[result([], SYNC), result([], DECISIONS)]):
                self.assertEqual(job.run(base=Path(tmp), state_dir=Path(tmp))[0], "PASS")
            self.assertFalse((Path(tmp) / job.LATCH).exists())
            lease = job.mark_quarantine(Path(tmp))
            marker = Path(tmp) / job.LATCH
            marker.write_text("different owner operation")
            with self.assertRaises(job.ReviewJobBlocked):
                job.finish_verified_run(Path(tmp), lease)
            self.assertEqual(marker.read_text(), "different owner operation")

    def test_bad_types_and_rows_cannot_pass(self):
        for payload in ({**SYNC, "review_count": True},
                        {**SYNC, "appended_count": -2},
                        {**SYNC, "status": "PLAN_ONLY"}):
            with self.subTest(payload=payload), self.assertRaises(job.ReviewJobBlocked):
                job.validated_result("sync", 0, json.dumps(payload))
        with self.assertRaises(job.ReviewJobBlocked):
            job.validated_result("decisions", 1, json.dumps(DECISIONS))

    def test_missing_or_symlink_state_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(job.ReviewJobBlocked, "STATE_DIR_INVALID"):
                job.run(state_dir=Path(tmp) / "missing")
            link = Path(tmp) / "link"
            link.symlink_to(Path(tmp))
            with self.assertRaisesRegex(job.ReviewJobBlocked, "STATE_DIR_INVALID"):
                job.run(state_dir=link)


if __name__ == "__main__":
    unittest.main()
