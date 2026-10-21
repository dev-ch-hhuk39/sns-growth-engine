#!/usr/bin/env python3
"""Scheduled slot inspection is hosted/read-only; manual recovery retains VPS authority."""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "content-slot-recovery.yml"


class HostedScheduledSlotAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.raw = WORKFLOW.read_text(encoding="utf-8")
        cls.spec = yaml.safe_load(cls.raw)
        cls.audit = cls.spec["jobs"]["audit-missed-slots"]
        cls.manual = cls.spec["jobs"]["recover-missed-slots"]

    def test_schedule_is_hourly_not_twelve_times_per_hour(self) -> None:
        self.assertIn('- cron: "13 * * * *"', self.raw)
        self.assertNotIn("3-58/5", self.raw)
        self.assertIn("if: github.event_name == 'schedule'", self.raw)

    def test_scheduled_scan_is_standard_hosted_and_account_scoped(self) -> None:
        self.assertEqual(self.audit["runs-on"], "ubuntu-latest")
        self.assertEqual(self.audit["environment"], "production")
        self.assertEqual(self.audit["strategy"]["max-parallel"], 1)
        self.assertEqual(
            self.audit["strategy"]["matrix"]["account"],
            ["night_scout", "liver_manager", "beauty_account"],
        )
        self.assertEqual(self.audit["if"], "github.event_name == 'schedule'")

    def test_hosted_steps_are_strictly_read_only_and_redacted(self) -> None:
        steps = self.audit["steps"]
        commands = "\n".join(str(s.get("run", "")) for s in steps)
        self.assertIn("reconcile_due_production_slots.py", commands)
        self.assertIn("--dry-run", commands)
        self.assertIn("audit_file", commands)
        self.assertIn("summarize_readonly_slot_audit.py", commands)
        self.assertIn("--report-file", commands)
        self.assertIn('audit_rc=$?', commands)
        self.assertIn('summary_rc=$?', commands)
        self.assertIn('if [ "$audit_rc" -eq 0 ] && [ "$summary_rc" -eq 0 ]', commands)
        self.assertNotIn('cat "$audit_file"', commands)
        self.assertNotIn('cat "$error_file"', commands)
        for forbidden in ("--apply", "--confirm-reconcile", "run_buffered_production_host.sh",
                          "ALLOW_REAL_THREADS_POST: \"true\"", "curl -X POST"):
            self.assertNotIn(forbidden, commands)
        for s in steps:
            self.assertNotIn("continue-on-error", s)
        for key in ("PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST",
                    "ALLOW_CLOUDINARY_UPLOAD", "ALLOW_VIDEO_DOWNLOAD"):
            self.assertEqual(self.spec["env"][key], "false")

    def test_manual_recovery_remains_vps_and_explicitly_approved(self) -> None:
        self.assertEqual(self.manual["if"], "github.event_name == 'workflow_dispatch'")
        self.assertEqual(self.manual["runs-on"], ["self-hosted", "Linux", "X64"])
        self.assertEqual(self.manual["strategy"]["max-parallel"], 1)
        guarded = [s for s in self.manual["steps"]
                   if s.get("name") == "Guard and backfill at most one slot per account"]
        self.assertEqual(len(guarded), 1)
        cond = guarded[0]["if"]
        for expected in ("github.event_name == 'workflow_dispatch'",
                         "github.event.inputs.confirm_recovery == 'true'",
                         "vars.SNS_OWNER_PUBLISH_APPROVED == 'true'"):
            self.assertIn(expected, cond)

    def test_scheduled_audit_cannot_be_confused_with_manual_job(self) -> None:
        self.assertNotEqual(self.audit["if"], self.manual["if"])
        self.assertNotIn("sns-growth-production-", str(self.audit.get("concurrency", "")))
        self.assertIn("sns-growth-production-", self.manual["concurrency"]["group"])


if __name__ == "__main__":
    unittest.main()
