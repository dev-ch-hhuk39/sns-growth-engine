#!/usr/bin/env python3
"""Enforce no-outbound legacy GitHub sender steps and sole buffered VPS recovery."""
from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github/workflows"
FROZEN_STEPS = {
    "autonomous-growth-loop-night-scout.yml": {"Apply autonomous Threads loop"},
    "autonomous-growth-loop-liver-manager.yml": {"Apply autonomous Threads loop"},
    "autonomous-growth-loop.yml": {"Apply autonomous Threads loop"},
    "beauty-threads-production.yml": {
        "Publish one scheduled strictly approved Beauty row",
        "Publish one manually confirmed approved READY text row",
        "Publish one exact human-approved Beauty media row",
    },
    "direct-reference-media-night-scout.yml": {"Dispatch one READY direct-media item"},
    "direct-reference-media-liver-manager.yml": {"Dispatch one READY direct-media item"},
    "media-growth-post-night-scout.yml": {"Post one saved approved media asset"},
    "media-growth-post-liver-manager.yml": {"Post one saved approved media asset"},
    "tiktok-shop-threads-onboarding.yml": {"Publish one exact human-reviewed canary"},
}


def workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def steps(w: dict) -> list[dict]:
    return [step for job in (w.get("jobs") or {}).values()
            for step in job.get("steps", [])]


class LegacyGitHubPublisherQuarantineTest(unittest.TestCase):
    def test_all_legacy_direct_publish_steps_immutably_disabled(self):
        for file, names in FROZEN_STEPS.items():
            parsed = workflow(file)
            for name in names:
                with self.subTest(file=file, name=name):
                    found = [step for step in steps(parsed) if step.get("name") == name]
                    self.assertEqual(len(found), 1)
                    self.assertEqual(found[0].get("if"), "${{ false }}")
                    self.assertEqual(found[0].get("env", {}).get("PUBLISH_ENABLED"), "true")

    def test_no_additional_unquarantined_workflow_publish_step(self):
        for path in sorted(WORKFLOWS.glob("*.yml")):
            parsed = workflow(path.name)
            for step in steps(parsed):
                env = step.get("env") or {}
                if env.get("PUBLISH_ENABLED") != "true" and env.get("ALLOW_REAL_THREADS_POST") != "true":
                    continue
                with self.subTest(file=path.name, step=step.get("name")):
                    if path.name == "content-slot-recovery.yml":
                        self.assertEqual(step.get("name"), "Guard and backfill at most one slot per account")
                        continue
                    if path.name == "threads-queue-worker.yml":
                        self.assertEqual(step.get("name"), "Process queue")
                        continue
                    self.assertIn(step.get("name"), FROZEN_STEPS.get(path.name, set()))
                    self.assertEqual(step.get("if"), "${{ false }}")

    def test_recovery_never_falls_back_to_legacy_publisher(self):
        w = workflow("content-slot-recovery.yml")
        recovery = w["jobs"]["recover-missed-slots"]
        self.assertIn("self-hosted", recovery["runs-on"])
        self.assertEqual(recovery["if"], "github.event_name == 'workflow_dispatch'")
        audit = w["jobs"]["audit-missed-slots"]
        self.assertEqual(audit["runs-on"], "ubuntu-latest")
        self.assertEqual(audit["if"], "github.event_name == 'schedule'")
        step = [s for s in steps(w) if s.get("name") == "Guard and backfill at most one slot per account"]
        self.assertEqual(len(step), 1)
        run = step[0]["run"]
        self.assertIn("scripts/run_buffered_production_host.sh", run)
        self.assertIn("BUFFERED_RUNTIME_INACTIVE_LEGACY_FALLBACK_DISABLED", run)
        self.assertNotIn("backfill_missed_content_slots.py", run)
        self.assertNotIn("--apply --confirm-backfill", run)

    def test_legacy_manual_queue_fails_before_any_mutating_steps(self):
        w = workflow("threads-queue-worker.yml")
        job_steps = steps(w)
        names = [s.get("name") for s in job_steps]
        guard = job_steps[names.index("Guard account and mode")]["run"]
        self.assertIn('"$MODE" = "real_post"', guard)
        self.assertIn('"$EXACT_QUEUE_APPROVAL" = "OWNER_APPROVED_EXACT_QUEUE"', guard)
        self.assertIn("LEGACY_GITHUB_DIRECT_POSTING_DISABLED_USE_BUFFERED_VPS", guard)
        self.assertIn("exit 78", guard)
        for name in ("Repair posted_results integrity", "Record exact Beauty queue approval", "Process queue"):
            self.assertLess(names.index("Guard account and mode"), names.index(name))

    def test_preparation_schedules_and_safe_workflows_are_retained(self):
        for file in (
            "autonomous-growth-loop-night-scout.yml",
            "autonomous-growth-loop-liver-manager.yml",
            "beauty-threads-production.yml",
            "direct-reference-media-night-scout.yml",
            "direct-reference-media-liver-manager.yml",
            "media-growth-post-night-scout.yml",
            "media-growth-post-liver-manager.yml",
        ):
            w = workflow(file)
            self.assertIn("schedule", w.get("on", w.get(True, {})))
            self.assertTrue(any(s.get("name", "").lower().find("dry-run") >= 0
                                or s.get("name", "").lower().find("prepare") >= 0
                                or s.get("name", "").lower().find("review") >= 0
                                for s in steps(w)), file)


if __name__ == "__main__":
    unittest.main()
