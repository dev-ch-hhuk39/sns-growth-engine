#!/usr/bin/env python3
"""No-credential preflight tests for the existing metrics collection worker."""
from __future__ import annotations

import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import process_threads_metric_jobs as worker  # noqa: E402


class MetricsApplyBeforeSheetsTests(unittest.TestCase):
    def run_cli(self, *argv: str, with_state=False):
        buffer=io.StringIO()
        with patch.object(worker.sys, "argv", ["metric-jobs", *argv]), \
             patch.object(
                 worker, "load_state",
                 return_value=(object(), [], [], []) if with_state else None,
                 side_effect=None if with_state else AssertionError(
                     "credentials_must_not_be_loaded_before_approval"
                 ),
             ) as load, redirect_stdout(buffer):
            code = worker.main()
        payload=json.loads(buffer.getvalue())
        return code,payload,load

    def test_apply_without_confirmation_rejected_before_loading_secrets(self):
        for args in (
            ("--apply","--use-sheets","--account-id","night_scout"),
            ("--apply","--use-sheets","--account-id","liver_manager"),
        ):
            with self.subTest(args=args):
                code,payload,load=self.run_cli(*args)
                self.assertEqual(code,1)
                self.assertEqual(payload["reason"],"apply_requires_confirm_metrics")
                self.assertFalse(payload["would_write"])
                load.assert_not_called()

    def test_conflicting_apply_and_dry_run_rejected_before_io(self):
        code,payload,load=self.run_cli(
            "--dry-run","--apply","--confirm-metrics",
            "--use-sheets","--account-id","night_scout",
        )
        self.assertEqual(code,1)
        self.assertEqual(payload["reason"],"dry_run_and_apply_are_mutually_exclusive")
        load.assert_not_called()

    def test_apply_does_not_allow_all_accounts_as_bulk(self):
        code,payload,load=self.run_cli(
            "--apply","--confirm-metrics","--use-sheets","--account-id","all",
        )
        self.assertEqual(code,1)
        self.assertEqual(payload["reason"],"apply_requires_one_account")
        load.assert_not_called()

    def test_invalid_batch_size_rejected_before_io(self):
        for count in ("0","51","-1"):
            with self.subTest(count=count):
                code,payload,load=self.run_cli(
                    "--apply","--confirm-metrics","--use-sheets",
                    "--account-id","night_scout","--max-jobs",count,
                )
                self.assertEqual(code,1)
                self.assertIn("max-jobs",payload["reason"])
                load.assert_not_called()

    def test_apply_cannot_omit_sheets_selection(self):
        code,payload,load=self.run_cli(
            "--apply","--confirm-metrics","--account-id","night_scout",
        )
        self.assertEqual(code,1)
        self.assertIn("--use-sheets",payload["reason"])
        load.assert_not_called()

    def test_explicit_readonly_plan_still_available(self):
        code,payload,load=self.run_cli(
            "--dry-run","--use-sheets","--account-id","night_scout",
            with_state=True,
        )
        self.assertEqual(code,0)
        self.assertEqual(payload["status"],"PLAN_ONLY")
        load.assert_called_once_with(apply=False)

    def test_explicit_one_account_apply_without_due_jobs_does_not_call_api(self):
        code,payload,load=self.run_cli(
            "--apply","--confirm-metrics","--use-sheets",
            "--account-id","night_scout",with_state=True,
        )
        self.assertEqual(code,0)
        self.assertEqual(payload["status"],"NO_DUE_JOBS")
        load.assert_called_once_with(apply=True)


if __name__=="__main__":
    unittest.main()
