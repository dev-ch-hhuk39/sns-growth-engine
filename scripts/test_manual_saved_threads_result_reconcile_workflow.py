#!/usr/bin/env python3
"""No-post/manual-only contract for repairing one independently proven saved post."""
from __future__ import annotations

import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/reconcile-single-saved-threads-post.yml"
EXACT_QUEUE_ID = "q_liver_manager_fallback_20260915140951_1_threads"


class SingleSavedThreadsReconciliationWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.doc = yaml.safe_load(cls.source)
        cls.job = cls.doc["jobs"]["reconcile-one-saved-result"]
        cls.steps = cls.job["steps"]

    def test_manual_only_main_and_production_environment(self):
        self.assertIn("  workflow_dispatch:", self.source)
        self.assertNotIn("\n  schedule:", self.source)
        self.assertNotIn("\n  push:", self.source)
        self.assertNotIn("\n  pull_request:", self.source)
        self.assertEqual(self.job["if"], "github.ref == 'refs/heads/main'")
        self.assertEqual(self.job["runs-on"], "ubuntu-latest")
        self.assertEqual(self.job["environment"], "production")
        self.assertEqual(self.doc["permissions"], {"contents": "read"})
        self.assertFalse(self.doc["concurrency"]["cancel-in-progress"])
        self.assertIn("sns-growth-production-liver-manager-", self.doc["concurrency"]["group"])

    def test_hardcoded_exact_queue_and_account_not_user_selected(self):
        env = self.job["env"]
        self.assertEqual(env["ACCOUNT_ID"], "liver_manager")
        self.assertEqual(env["EXPECTED_QUEUE_ID"], EXACT_QUEUE_ID)
        self.assertNotIn("queue_id:", self.source.split("on:", 1)[1].split("permissions:", 1)[0])
        self.assertIn("THREADS_ACCESS_TOKEN_LIVER_MANAGER", env)
        self.assertIn("THREADS_USER_ID_LIVER_MANAGER", env)
        self.assertIn("GCP_SA_JSON_BASE64", env)
        self.assertIn("SPREADSHEET_ID", env)

    def test_provider_proof_always_precedes_optional_update(self):
        named = {step.get("name"): i for i, step in enumerate(self.steps) if step.get("name")}
        proof = "Read-only saved result and authenticated Threads GET proof"
        apply = "Apply exact queue-only reconciliation after proof"
        guard = "Guard exact scope and manual confirmation"
        self.assertLess(named[guard], named[proof])
        self.assertLess(named[proof], named[apply])
        dry_command = str(self.steps[named[proof]]["run"])
        apply_command = str(self.steps[named[apply]]["run"])
        self.assertIn("--reconcile-saved-result-queue", dry_command)
        self.assertNotIn("--apply", dry_command)
        self.assertIn("--reconcile-saved-result-queue --apply", apply_command)
        cond = str(self.steps[named[apply]]["if"])
        self.assertIn("inputs.mode == 'apply-verified-repair'", cond)
        self.assertIn("inputs.confirmation == 'RECONCILE_ONE_POSTED_RESULT'", cond)
        self.assertIn('test "$REPAIR_CONFIRMATION" = "RECONCILE_ONE_POSTED_RESULT"', str(
            self.steps[named[guard]]["run"]
        ))

    def test_all_publishing_and_media_flags_remain_false(self):
        env = self.doc["env"]
        for flag in ("PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
                     "ALLOW_MEDIA_POSTS", "ALLOW_REAL_THREADS_VIDEO_POST",
                     "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT",
                     "ALLOW_CLOUDINARY_UPLOAD", "ALLOW_TRANSCRIPTION_API"):
            self.assertEqual(env[flag], "false", flag)
        for command in ("--confirm-real-post", "--confirm-upload",
                        "scripts/process_threads_queue.py",
                        "scripts/collect_threads_metrics.py"):
            self.assertNotIn(command, self.source)

    def test_read_only_is_default_and_mode_requires_confirm(self):
        inputs = self.doc.get("on") or self.doc.get(True)
        declared = inputs["workflow_dispatch"]["inputs"]
        self.assertEqual(declared["mode"]["default"], "verify-only")
        self.assertEqual(declared["mode"]["options"],
                         ["verify-only", "apply-verified-repair"])
        self.assertEqual(declared["confirmation"]["default"], "")


if __name__ == "__main__":
    unittest.main()
