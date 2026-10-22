#!/usr/bin/env python3
"""Synthetic-only checks for nested process exit status and private CI logs."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_autopilot_loop as loop


class AutopilotParentExitContract(unittest.TestCase):
    @staticmethod
    def _fake_step(code: int) -> dict:
        return {"cmd": "SECRET_PRIVATE_COMMAND", "returncode": code,
                "stdout_tail": "SECRET_PRIVATE_DRAFT_WITH_UNPUBLISHED_QUEUE_ID",
                "stderr_tail": "SECRET_PRIVATE_PROVIDER_CREDENTIAL"}

    def _call(self, codes, *, summary=True, apply=True):
        args = ["run_autopilot_loop.py", "--account-id", "night_scout",
                "--auto-ready", "--skip-real-post", "--use-sheets"]
        if apply:
            args += ["--apply", "--confirm-run"]
        else:
            args += ["--dry-run"]
        if summary:
            args += ["--summary-only"]
        output = io.StringIO()
        with patch.object(sys, "argv", args), \
                patch.object(loop, "load_rules", return_value={}), \
                patch.object(loop, "auto_post_gate",
                             return_value={"allowed": False}), \
                patch.object(loop, "_run",
                             side_effect=[self._fake_step(c) for c in codes]) as run, \
                contextlib.redirect_stdout(output):
            exit_code = loop.main()
        return exit_code, json.loads(output.getvalue()), output.getvalue(), run.call_args_list

    def test_nested_failed_autoready_returns_nonzero_and_redacts(self):
        exit_code, data, printed, calls = self._call([0, 1, 0])
        self.assertEqual(exit_code, 1)
        self.assertEqual(data["status"], "FAILED")
        self.assertEqual(data["failed_steps"], 1)
        self.assertEqual(data["steps_checked"], 3)
        self.assertEqual(data["account_id"], "night_scout")
        self.assertFalse(data["real_post_allowed"])
        self.assertNotIn("SECRET_PRIVATE", printed)
        self.assertIn("--dry-run", calls[2].args[0])
        self.assertNotIn("--confirm-real-post", calls[2].args[0])

    def test_all_nested_success_returns_zero_without_draft_leaks(self):
        exit_code, data, printed, _ = self._call([0, 0, 0])
        self.assertEqual(exit_code, 0)
        self.assertEqual(data["status"], "PASS")
        self.assertEqual(data["failed_steps"], 0)
        self.assertNotIn("SECRET_PRIVATE", printed)

    def test_full_legacy_report_has_final_status_not_will_run(self):
        exit_code, data, _, _ = self._call([0, 0, 0], summary=False)
        self.assertEqual(exit_code, 0)
        self.assertEqual(data["status"], "DONE")

    def test_dry_run_nested_failure_is_not_silent(self):
        exit_code, data, printed, _ = self._call([1, 0, 0, 0], apply=False)
        self.assertEqual(exit_code, 1)
        self.assertEqual(data["status"], "FAILED")
        self.assertEqual(data["mode"], "dry-run")
        self.assertNotIn("SECRET_PRIVATE", printed)

    def test_missing_returncode_fails_closed(self):
        plan = {"account_id": "night_scout", "auto_post_gate": {"allowed": False}}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = loop._report_outcome(plan, [{}], mode="apply", summary_only=True)
        self.assertEqual(exit_code, 1)
        self.assertEqual(json.loads(output.getvalue())["failed_steps"], 1)


if __name__ == "__main__":
    unittest.main()
