#!/usr/bin/env python3
"""No-post scoped READY pilot synthetic tests; zero external API calls."""
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


ARGS = [
    "run_autopilot_loop.py", "--apply", "--confirm-run",
    "--account-id", "night_scout", "--auto-ready", "--ready-only",
    "--max-ready", "1", "--use-sheets", "--skip-real-post", "--summary-only",
]


class TextReadyOnlyTests(unittest.TestCase):
    def run_mode(self, codes, args=None):
        captured = io.StringIO()
        malicious = "PRIVATE_TOKEN_OR_UNPUBLISHED_QUEUE_TEXT"
        child = [
            {"cmd": malicious, "returncode": status,
             "stdout_tail": malicious, "stderr_tail": malicious}
            for status in codes
        ]
        with (
            patch.object(sys, "argv", args or ARGS),
            patch.object(loop, "load_rules", return_value={}),
            patch.object(loop, "auto_post_gate", return_value={"allowed": False}),
            patch.object(loop, "_run", side_effect=child) as process,
            contextlib.redirect_stdout(captured),
        ):
            exit_code = loop.main()
        return exit_code, json.loads(captured.getvalue()), process.call_args_list, captured.getvalue()

    def test_ready_only_has_correct_separated_steps_and_no_publisher(self):
        code, report, calls, printed = self.run_mode([0, 0, 0])
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["steps_checked"], 3)
        self.assertFalse(report["real_post_allowed"])
        self.assertEqual(
            [x["status"] for x in report["stage_statuses"]],
            ["PASS", "PASS", "PASS"],
        )
        self.assertEqual(
            [x["stage"] for x in report["stage_statuses"]],
            ["TEXT_PREFLIGHT", "AUTO_READY_APPLY", "TEXT_POSTVERIFY"],
        )
        self.assertEqual(len(calls), 3)
        before = calls[0].args[0]
        approve = calls[1].args[0]
        after = calls[2].args[0]
        self.assertEqual(before, after)
        self.assertIn("--text-inventory-scope", before)
        self.assertIn("--account-id", before)
        self.assertIn("--skip-setup", approve)
        self.assertIn("--confirm-auto-ready", approve)
        self.assertNotIn("--confirm-real-post", " ".join(str(x) for x in calls))
        self.assertNotIn("process_threads_queue.py", str(calls))
        self.assertNotIn("PRIVATE_TOKEN", printed)

    def test_failed_text_preflight_blocks_every_write_and_post(self):
        code, report, calls, printed = self.run_mode([1])
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            [x["status"] for x in report["stage_statuses"]],
            ["FAILED", "NOT_RUN", "NOT_RUN"],
        )
        self.assertNotIn("PRIVATE_TOKEN", printed)

    def test_ambiguous_apply_still_checks_integrity_and_fails(self):
        code, report, calls, printed = self.run_mode([0, 1, 0])
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 3)
        self.assertEqual(report["failed_steps"], 1)
        self.assertEqual(
            [x["status"] for x in report["stage_statuses"]],
            ["PASS", "FAILED", "PASS"],
        )
        self.assertNotIn("PRIVATE_TOKEN", printed)

    def test_failed_postverify_blocks_completion(self):
        code, report, calls, _ = self.run_mode([0, 0, 2])
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["stage_statuses"][-1]["status"], "FAILED")
        self.assertEqual(len(calls), 3)

    def test_invalid_authority_never_starts_step(self):
        for changes in (
            ["--auto-post"],
            ["--confirm-real-post"],
            ["--max-ready", "4"],
        ):
            code, report, calls, _ = self.run_mode(
                [], args=ARGS + changes
            )
            self.assertEqual(code, 2)
            self.assertEqual(report["reason"], "READY_ONLY_SCOPE_INVALID")
            self.assertEqual(len(calls), 0)

        for removed in ("--skip-real-post", "--use-sheets", "--auto-ready", "--confirm-run"):
            invalid = [x for x in ARGS if x != removed]
            code, report, calls, _ = self.run_mode([], args=invalid)
            self.assertEqual(code, 2)
            self.assertEqual(report["reason"], "READY_ONLY_SCOPE_INVALID")
            self.assertEqual(len(calls), 0)

    def test_workflow_uses_scoped_mode_and_retains_two_sheets_verifiers(self):
        import yaml
        root = Path(__file__).resolve().parents[1]
        steps = yaml.safe_load(
            (root / ".github/workflows/autopilot-auto-ready.yml").read_text()
        )["jobs"]["auto-ready"]["steps"]
        mapped = {step.get("name"): step for step in steps}
        script = mapped["AUTO_READY apply only"]["run"]
        self.assertIn("--ready-only", script)
        self.assertIn("--skip-real-post", script)
        self.assertNotIn("--confirm-real-post", script)
        self.assertIn("--verify-only --text-inventory-scope",
                      mapped["Verify Sheets before AUTO_READY"]["run"])
        self.assertIn("--verify-only --text-inventory-scope",
                      mapped["Verify Sheets after AUTO_READY"]["run"])


if __name__ == "__main__":
    unittest.main()
