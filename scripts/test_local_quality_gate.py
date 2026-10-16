#!/usr/bin/env python3
"""Non-network tests for the optional Mac-only QA command."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_local_quality_gate as gate  # noqa: E402


class LocalQualityGateContractTests(unittest.TestCase):
    def test_credentials_are_not_copied_to_test_environment(self):
        with patch.dict(os.environ, {
            "TEST_SAFE_VAR": "yes",
            "FAKE_GITHUB_TOKEN": "masked",
            "GOOGLE_APPLICATION_CREDENTIALS": "/secrets/key.json",
            "TEST_API_KEY": "masked",
            "AWS_SECRET_ACCESS_KEY": "masked",
            "UNRELATED_COOKIE": "masked",
        }):
            result = gate.local_env()
        self.assertEqual(result["TEST_SAFE_VAR"], "yes")
        for key in ("FAKE_GITHUB_TOKEN", "GOOGLE_APPLICATION_CREDENTIALS",
                    "TEST_API_KEY", "AWS_SECRET_ACCESS_KEY", "UNRELATED_COOKIE"):
            self.assertNotIn(key, result)

    def test_outputs_must_be_outside_checkout(self):
        with self.assertRaisesRegex(ValueError, "report_must_be_outside_repository"):
            gate._safe_output(gate.ROOT / "do_not_create.json")
        with self.assertRaisesRegex(ValueError, "report_requires_absolute_path"):
            gate._safe_output(Path("relative.json"))

    def _captured_run(self, mode, skip_scan=False):
        seen = []
        with tempfile.TemporaryDirectory(prefix="sns-local-gate-") as directory:
            base = Path(directory)
            def fake_record(name, argv, *, timeout, env, log_dir):
                seen.append((name, argv, timeout))
                return {
                    "name": name, "status": "PASS",
                    "exit_code": 0, "log_path": str(log_dir / (name + ".log")),
                }
            with patch.object(gate, "_record", side_effect=fake_record):
                report = gate.run(
                    mode=mode, output=base / "report.json",
                    log_dir=base / "logs",
                    skip_git_history_scan=skip_scan,
                )
            stored = (base / "report.json").read_text(encoding="utf-8")
            self.assertIn('"github_actions_invoked": false', stored)
            self.assertEqual(report["status"], "PASS")
            self.assertFalse(report["production_deployment_performed"])
            self.assertFalse(report["sns_post_performed"])
        return seen

    def test_focused_mode_runs_only_safe_local_tools(self):
        seen = self._captured_run("focused")
        names = [name for name, _, _ in seen]
        self.assertIn("test_metrics_reservation_recovery", names)
        self.assertIn("gitleaks_local", names)
        self.assertNotIn("repository_offline", names)
        for _, argv, _ in seen:
            self.assertNotIn("gh", argv)
            self.assertNotIn("ssh", argv)
            self.assertNotIn("git push", " ".join(argv))
            self.assertNotIn("workflow_dispatch", " ".join(argv))

    def test_full_mode_uses_offline_repository_and_static_workflow_tests(self):
        seen = self._captured_run("full")
        mapping = {name: argv for name, argv, _ in seen}
        self.assertIn("repository_offline", mapping)
        self.assertIn("workflow_static_safety", mapping)
        self.assertIn("gitleaks_local", mapping)
        self.assertIn("run_repository_tests.py", " ".join(mapping["repository_offline"]))
        self.assertNotIn("--include-external-probes", mapping["repository_offline"])
        self.assertNotIn("workflow_dispatch", " ".join(mapping["workflow_static_safety"]))

    def test_failure_is_reported_as_failure(self):
        with tempfile.TemporaryDirectory(prefix="sns-local-gate-") as directory:
            base = Path(directory)
            with patch.object(gate, "_record", return_value={
                "name": "mock", "status": "FAIL",
                "exit_code": 1, "log_path": str(base / "fake.log"),
            }):
                report = gate.run(
                    mode="focused", output=base / "report.json",
                    log_dir=base / "logs", skip_git_history_scan=True,
                )
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(report["checks"])
        self.assertFalse(report["github_actions_invoked"])

    def test_skip_history_scanner_requires_explicit_flag(self):
        seen = self._captured_run("focused", skip_scan=True)
        self.assertNotIn("gitleaks_local", {name for name, _, _ in seen})

    def test_full_mode_never_skips_secret_history_scan(self):
        with tempfile.TemporaryDirectory(prefix="sns-local-gate-") as directory:
            base = Path(directory)
            with self.assertRaisesRegex(
                ValueError, "full_mode_requires_local_secret_history_scan",
            ):
                gate.run(
                    mode="full", output=base / "report.json",
                    log_dir=base / "logs", skip_git_history_scan=True,
                )


if __name__ == "__main__":
    unittest.main()
