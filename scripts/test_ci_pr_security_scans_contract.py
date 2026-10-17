#!/usr/bin/env python3
"""Ensure PR builds actually execute dependency and full-history secret scans."""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


class PrSecurityScanContractTests(unittest.TestCase):
    def setUp(self):
        self.data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.jobs = self.data["jobs"]

    def test_prs_run_both_security_scans(self):
        for name in ("dependency-audit", "secret-history-scan"):
            job = self.jobs[name]
            self.assertIn("github.event_name == 'pull_request'", job.get("if", ""), name)
            self.assertIn("github.event_name == 'schedule'", job.get("if", ""), name)
            self.assertNotIn("continue-on-error", job, name)
            self.assertEqual(job["runs-on"], "ubuntu-latest", name)
            self.assertLessEqual(job["timeout-minutes"], 15, name)

    def test_dependency_scan_has_all_requirements_including_ci(self):
        steps = self.jobs["dependency-audit"]["steps"]
        action = next(step for step in steps if str(step.get("uses", "")).startswith("pypa/gh-action-pip-audit@"))
        sources = action["with"]["inputs"]
        for name in ("requirements.txt", "requirements-acquisition.txt",
                     "requirements-media-runtime.txt", "requirements-ci.txt"):
            self.assertIn(name, sources)

    def test_history_scan_checks_out_entire_history_without_credentials(self):
        steps = self.jobs["secret-history-scan"]["steps"]
        checkout = next(step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@"))
        self.assertEqual(checkout["with"]["fetch-depth"], 0)
        self.assertFalse(checkout["with"]["persist-credentials"])
        self.assertTrue(any(str(step.get("uses", "")).startswith("gitleaks/gitleaks-action@")
                            for step in steps))
        self.assertEqual(self.data["permissions"], {"contents": "read"})

    def test_ci_keeps_tests_and_diff_secret_gate(self):
        self.assertIn("tests", self.jobs)
        self.assertIn("pr-gate", self.jobs)
        gates = str(self.jobs["pr-gate"]["steps"])
        self.assertIn("Secret diff scan", gates)
        self.assertIn("gitleaks/gitleaks-action@", gates)


if __name__ == "__main__":
    unittest.main()
