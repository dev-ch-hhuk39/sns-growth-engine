#!/usr/bin/env python3
"""Synthetic-only tests for public-log safe READY error classification."""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import yaml

import ready_inventory_diagnostics as diagnostics


class PrivateReadyFailureTests(unittest.TestCase):
    def test_bounded_known_hints_without_payload_echo(self):
        examples = (
            ("requests.exceptions.ReadTimeout: private-caption-ONE", "PROCESS_TIMEOUT"),
            ("ResourceExhausted quota exceeded private-token-TWO", "API_QUOTA_OR_RATE_LIMIT"),
            ("PermissionError private-sheet-id-THREE", "PERMISSION_REJECTED"),
            ("ServiceUnavailable private-draft-FOUR", "PROVIDER_UNAVAILABLE"),
            ("Traceback (most recent call last) private-token-FIVE", "PYTHON_EXCEPTION"),
            ("private post text is never printed", "UNCLASSIFIED_FAILURE"),
        )
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "stderr.txt"
            for private_text, expected in examples:
                report.write_text(private_text, encoding="utf-8")
                self.assertEqual(diagnostics.classify_private_stderr(report), expected)

    def test_empty_or_unavailable_stderr(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            empty = root / "empty.txt"
            empty.write_text("")
            self.assertEqual(
                diagnostics.classify_private_stderr(empty), "EMPTY_PRIVATE_DIAGNOSTICS"
            )
            self.assertEqual(
                diagnostics.classify_private_stderr(root / "missing"),
                "PRIVATE_DIAGNOSTICS_UNAVAILABLE",
            )
            oversized = root / "oversized"
            oversized.write_bytes(b"x" * 2_000_001)
            self.assertEqual(
                diagnostics.classify_private_stderr(oversized),
                "PRIVATE_DIAGNOSTICS_UNAVAILABLE",
            )

    def test_symlink_never_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "source"
            target.write_text("PermissionError private-value", encoding="utf-8")
            linked = root / "linked"
            linked.symlink_to(target)
            self.assertEqual(
                diagnostics.classify_private_stderr(linked),
                "PRIVATE_DIAGNOSTICS_UNAVAILABLE",
            )

    def test_invalid_json_cli_prints_hint_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            stderr = root / "stderr.txt"
            report.write_text("{UNPUBLISHED_DRAFT_PRIVATE", encoding="utf-8")
            stderr.write_text(
                "ReadTimeout received token=SECRET_VALUE_PRIVATE",
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = diagnostics.main([
                    "--account-id", "night_scout",
                    "--report", str(report),
                    "--private-stderr", str(stderr),
                ])
            self.assertEqual(status, 2)
            self.assertIn("PRIVATE_FAILURE_HINT=PROCESS_TIMEOUT", output.getvalue())
            self.assertNotIn("SECRET_VALUE_PRIVATE", output.getvalue())
            self.assertNotIn("UNPUBLISHED_DRAFT_PRIVATE", output.getvalue())

    def test_valid_json_keeps_existing_scope_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            stderr = root / "stderr.txt"
            report.write_text(json.dumps({"status": "PASS", "results": [
                {"account_id": "night_scout", "delivery_slo": "PASS"}
            ]}), encoding="utf-8")
            stderr.write_text("SECRET_DRAFT_VALUE", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                status = diagnostics.main([
                    "--account-id", "night_scout",
                    "--report", str(report),
                    "--private-stderr", str(stderr),
                ])
            self.assertEqual(status, 0)
            self.assertIn("Delivery slots: 1/1", output.getvalue())
            self.assertNotIn("SECRET", output.getvalue())

    def test_public_workflows_only_use_private_tempfile(self):
        root = Path(__file__).resolve().parents[1] / ".github/workflows"
        cases = (
            ("autopilot-auto-ready.yml", "auto-ready", 4),
            ("production-autopilot-aftercare.yml", "aftercare", 2),
        )
        for filename, jobname, expected in cases:
            doc = yaml.safe_load((root / filename).read_text(encoding="utf-8"))
            scripts = "\n".join(step.get("run", "") for step in doc["jobs"][jobname]["steps"])
            self.assertEqual(scripts.count('--private-stderr "$ready_stderr"'), expected)
            self.assertIn('ready_stderr="$(mktemp)"', scripts)
            self.assertNotIn("cat \"$ready_stderr\"", scripts)
            self.assertNotIn("cat \"$ready_report\"", scripts)
            self.assertEqual(doc["env"]["ALLOW_REAL_THREADS_POST"], "false")
            self.assertEqual(doc["env"]["ALLOW_REAL_X_POST"], "false")


if __name__ == "__main__":
    unittest.main()
