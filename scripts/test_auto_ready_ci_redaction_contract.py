#!/usr/bin/env python3
"""GitHub-hosted public logs contain no raw publication candidate reports."""
from __future__ import annotations

import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/autopilot-auto-ready.yml"
AFTERCARE = ROOT / ".github/workflows/production-autopilot-aftercare.yml"


class PublicAutoReadyLogContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        document = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        cls.steps = {s.get("name"): s for s in document["jobs"]["auto-ready"]["steps"]}
        cls.env = document["env"]

    def test_publishing_remains_off(self):
        for name in ("PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST"):
            self.assertEqual(self.env[name], "false")

    def test_ready_source_report_private_and_diagnostic_only(self):
        code = self.steps["Maintain next text-slot READY inventory"]["run"]
        self.assertIn('ready_report="$(mktemp)"', code)
        self.assertIn('> "$ready_report" 2>&1', code)
        self.assertIn('ready_inventory_diagnostics.py', code)
        self.assertIn("exit 1", code)
        self.assertIn("trap 'rm -f \"$ready_report\"' EXIT", code)

    def test_evergreen_result_redacted_before_emission(self):
        code = self.steps["Refill validated non-AI emergency bank"]["run"]
        self.assertIn('bank_report="$(mktemp)"', code)
        self.assertIn('> "$bank_report" 2>&1', code)
        self.assertIn("ready_evergreen_bank_summary.py", code)
        self.assertIn("exit 1", code)
        self.assertIn("trap 'rm -f \"$bank_report\"' EXIT", code)

    def test_autopilot_status_only_and_fails_closed(self):
        code = self.steps["AUTO_READY apply only"]["run"]
        self.assertIn("--summary-only", code)
        self.assertIn("--skip-real-post", code)
        self.assertNotIn("--confirm-real-post", code)


    def test_aftercare_ready_and_evergreen_reports_are_private(self):
        doc = yaml.safe_load(AFTERCARE.read_text(encoding="utf-8"))
        steps = {step.get("name"): step for step in doc["jobs"]["aftercare"]["steps"]}
        code = steps["Maintain next 24h READY inventory from measured PDCA"]["run"]
        self.assertIn('> "$ready_report" 2>&1', code)
        self.assertIn('> "$bank_report" 2>&1', code)
        self.assertIn("ready_inventory_diagnostics.py", code)
        self.assertIn("ready_evergreen_bank_summary.py", code)
        self.assertIn("exit 1", code)
        self.assertEqual(doc["env"]["ALLOW_REAL_THREADS_POST"], "false")
        self.assertEqual(doc["env"]["ALLOW_REAL_X_POST"], "false")


if __name__ == "__main__":
    unittest.main()
