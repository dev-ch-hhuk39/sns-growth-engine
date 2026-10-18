#!/usr/bin/env python3
"""Scheduled recovery can inspect missed slots but never publish to Threads."""
from __future__ import annotations

import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/content-slot-recovery.yml"


class ContentSlotRecoveryApprovalTests(unittest.TestCase):
    def setUp(self):
        self.spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.job = self.spec["jobs"]["recover-missed-slots"]
        self.steps = self.job["steps"]

    def test_scheduled_backfill_requires_explicit_manual_owner_approval(self):
        step = next(s for s in self.steps
                    if s.get("name") == "Guard and backfill at most one slot per account")
        condition = step["if"]
        self.assertNotIn("github.event_name == 'schedule'", condition)
        self.assertIn("github.event_name == 'workflow_dispatch'", condition)
        self.assertIn("github.event.inputs.confirm_recovery == 'true'", condition)
        self.assertIn("github.event.inputs.dry_run_only != 'true'", condition)
        self.assertIn("vars.SNS_OWNER_PUBLISH_APPROVED == 'true'", condition)
        self.assertEqual(step["env"]["PUBLISH_ENABLED"], "true")
        self.assertEqual(step["env"]["ALLOW_REAL_THREADS_POST"], "true")

    def test_job_defaults_to_no_publish_and_keeps_inspection(self):
        env = self.spec["env"]
        for flag in ("PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
                     "ALLOW_CLOUDINARY_UPLOAD", "ALLOW_VIDEO_DOWNLOAD"):
            self.assertEqual(env[flag], "false")
        self.assertTrue(any(s.get("name") == "Dry-run missed-slot scan" for s in self.steps))
        self.assertEqual(self.job["strategy"]["max-parallel"], 1)

    def test_dispatch_alone_cannot_authorize_external_post(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("default: \"false\"", text)
        self.assertNotIn("if: github.event_name == 'schedule' ||", text)
        self.assertIn("SNS_OWNER_PUBLISH_APPROVED", text)


if __name__ == "__main__":
    unittest.main()
