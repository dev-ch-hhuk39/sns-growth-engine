#!/usr/bin/env python3
"""Synthetic log-classification tests: only fixed bank codes may be public."""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ready_inventory_diagnostics as diag
import ready_evergreen_bank_summary as bank_summary


class FixedEvergreenPrivateErrorTests(unittest.TestCase):
    def test_exact_known_readback_errors_are_named_without_traces(self):
        with tempfile.TemporaryDirectory() as root:
            stderr = Path(root) / "private-stderr"
            for known in sorted(diag.SAFE_EVERGREEN_EXCEPTION_CODES):
                with self.subTest(known=known):
                    stderr.write_text(
                        'Traceback (most recent call last):\n'
                        '  File "/private/user/secret/app.py", line 421, in fail\n'
                        '    raise RuntimeError(private_token)\n'
                        'RuntimeError: ' + known + '\n',
                        encoding="utf-8",
                    )
                    self.assertEqual(diag.classify_private_stderr(stderr), known)
                    self.assertEqual(diag.fixed_evergreen_exception_hint(
                        stderr.read_text()), known)

    def test_untrusted_errors_or_extra_content_cannot_become_public_codes(self):
        raw_cases = (
            'RuntimeError: SECRET_PRIVATE_QUEUE_TOKEN',
            'RuntimeError: EVERGREEN_BATCH_READ_AFTER_WRITE_FAILED PRIVATE_SECRET',
            'RuntimeError: EVERGREEN_BATCH_READ_AFTER_WRITE_FAILED\n'
            'SECRET_PRIVATE_TOKEN_SAVED',
            'Provider wrote EVERGREEN_BATCH_READ_AFTER_WRITE_FAILED',
            'KeyError: EVERGREEN_BATCH_READ_AFTER_WRITE_FAILED',
        )
        expected = ("", "", "EVERGREEN_BATCH_READ_AFTER_WRITE_FAILED", "", "")
        for raw, result in zip(raw_cases, expected):
            with self.subTest(raw=raw[:38]):
                self.assertEqual(diag.fixed_evergreen_exception_hint(raw), result)

    def test_quota_or_timeout_remains_higher_priority(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "private-stderr"
            p.write_text(
                "Traceback (most recent call last):\n"
                "RuntimeError: EVERGREEN_BATCH_READ_AFTER_WRITE_FAILED\n"
                "RESOURCE_EXHAUSTED 429 too many requests\n",
                encoding="utf-8",
            )
            self.assertEqual(diag.classify_private_stderr(p), "API_QUOTA_OR_RATE_LIMIT")
            p.write_text(
                "Traceback (most recent call last):\n"
                "RuntimeError: EVERGREEN_BATCH_READ_AFTER_WRITE_FAILED\n"
                "TimeoutExpired private queued token\n", encoding="utf-8",
            )
            self.assertEqual(diag.classify_private_stderr(p), "PROCESS_TIMEOUT")

    def test_public_evergreen_summary_does_not_log_private_stderr_text(self):
        with tempfile.TemporaryDirectory() as root:
            report = Path(root) / "report"
            stderr = Path(root) / "stderr"
            report.write_text("{INVALID_SECRET_PRIVATE_REPORT", encoding="utf-8")
            stderr.write_text(
                "Traceback (most recent call last):\n"
                '  File "/private/data/PRIVATE_PATH", line 12\n'
                "RuntimeError: EVERGREEN_ADMISSION_RECEIPT_UNVERIFIED\n"
                "PRIVATE_POST_TEXT_MUST_NOT_APPEAR\n", encoding="utf-8",
            )
            out = io.StringIO()
            with (patch("sys.argv", [
                "ready_evergreen_bank_summary.py", "--account-id", "beauty_account",
                "--report", str(report), "--private-stderr", str(stderr),
            ]), contextlib.redirect_stdout(out)):
                rc = bank_summary.main()
            self.assertEqual(rc, 2)
            self.assertIn(
                "PRIVATE_FAILURE_HINT=EVERGREEN_ADMISSION_RECEIPT_UNVERIFIED",
                out.getvalue(),
            )
            self.assertNotIn("PRIVATE_POST_TEXT", out.getvalue())
            self.assertNotIn("PRIVATE_PATH", out.getvalue())
            self.assertNotIn("INVALID_SECRET", out.getvalue())

    def test_symlinked_private_stderr_never_followed(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "secret"
            source.write_text(
                "RuntimeError: EVERGREEN_BATCH_READ_AFTER_WRITE_FAILED", encoding="utf-8",
            )
            link = Path(root) / "link"
            link.symlink_to(source)
            self.assertEqual(
                diag.classify_private_stderr(link), "PRIVATE_DIAGNOSTICS_UNAVAILABLE",
            )


if __name__ == "__main__":
    unittest.main()
