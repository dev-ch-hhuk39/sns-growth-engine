#!/usr/bin/env python3
"""Offline contract for the one-time, no-post historical Threads queue repair."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / ".github/workflows/sns-once-reconcile-saved-threads-result.yml"
EXACT_QUEUE = "q_liver_manager_fallback_20260915140951_1_threads"


class OneShotSavedResultWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = PATH.read_text(encoding="utf-8")
        cls.doc = yaml.safe_load(cls.source)
        cls.job = cls.doc["jobs"]["verified-saved-result-queue-only"]
        cls.steps = cls.job["steps"]

    def test_canonical_workflow_inventory_tracks_new_file(self):
        contract = json.loads((ROOT / "config/reference_first_completion.json").read_text(encoding="utf-8"))
        listed = contract["workflow_classification"]["canonical"]
        self.assertEqual(listed.count(PATH.name), 1)

    def test_only_first_main_file_introduction_triggers(self):
        triggers = self.doc.get("on", self.doc.get(True))
        self.assertEqual(set(triggers), {"push"})
        self.assertEqual(triggers["push"]["branches"], ["main"])
        self.assertEqual(triggers["push"]["paths"], [".github/workflows/sns-once-reconcile-saved-threads-result.yml"])
        self.assertIn("github.ref == 'refs/heads/main'", self.job["if"])
        self.assertEqual(self.job["runs-on"], "ubuntu-latest")
        self.assertEqual(self.job["environment"], "production")
        self.assertEqual(self.doc["permissions"], {"contents": "read"})
        self.assertFalse(self.doc["concurrency"]["cancel-in-progress"])
        self.assertEqual(self.steps[0]["with"]["fetch-depth"], 2)

    def test_guard_rejects_rerun_existing_file_and_missing_before(self):
        guard = next(x["run"] for x in self.steps if x.get("name") == "Prove one-shot main introduction and immutable target")
        for marker in (
            'test "$GITHUB_RUN_ATTEMPT" = "1"',
            'test "$BEFORE_SHA" != "0000000000000000000000000000000000000000"',
            'git cat-file -e "$BEFORE_SHA^{commit}"',
            'git cat-file -e "$BEFORE_SHA:$TARGET_WORKFLOW"',
            'git cat-file -e "$GITHUB_SHA:$TARGET_WORKFLOW"',
            "exit 2",
        ):
            self.assertIn(marker, guard)
        self.assertIn("SNS_MASTER_SHEET_ID", guard)
        self.assertIn("THREADS_USER_ID_LIVER_MANAGER", guard)

    def test_proof_precedes_one_exact_queue_only_apply(self):
        names = [x.get("name", "") for x in self.steps]
        proof = names.index("Read-only authenticated provider match")
        apply = names.index("Apply one queue-only repair with read-after-write")
        self.assertLess(proof, apply)
        source_proof = self.steps[proof]["run"]
        source_apply = self.steps[apply]["run"]
        self.assertIn("--reconcile-saved-result-queue", source_proof)
        self.assertNotIn("--apply", source_proof)
        self.assertIn('"status": "PLAN_ONLY"', source_proof)
        self.assertIn("--reconcile-saved-result-queue --apply", source_apply)
        self.assertIn('"status": "RECONCILED_QUEUE_ONLY"', source_apply)
        self.assertIn("no automatic retry", source_apply.lower())
        self.assertEqual(self.job["env"]["ACCOUNT_ID"], "liver_manager")
        self.assertEqual(self.job["env"]["EXPECTED_QUEUE_ID"], EXACT_QUEUE)

    def test_no_post_secrets_or_raw_provider_logging(self):
        env = self.doc["env"]
        for flag in (
            "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
            "ALLOW_MEDIA_POSTS", "ALLOW_REAL_THREADS_VIDEO_POST",
            "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT",
            "ALLOW_CLOUDINARY_UPLOAD", "ALLOW_TRANSCRIPTION_API",
        ):
            self.assertEqual(env[flag], "false", flag)
        for banned in (
            "--confirm-real-post", "scripts/process_threads_queue.py",
            "publish_threads_post.py", "gh secret", "--repair-existing-save",
            "--skip-api-lookup", "curl -X POST",
        ):
            self.assertNotIn(banned, self.source)
        self.assertIn('> "$RUNNER_TEMP/reconcile-verify.json" 2> "$RUNNER_TEMP/reconcile-verify.err"', self.source)
        self.assertIn('> "$RUNNER_TEMP/reconcile-apply.json" 2> "$RUNNER_TEMP/reconcile-apply.err"', self.source)

    def test_one_shot_cannot_change_any_other_table(self):
        self.assertNotIn("append_rows", self.source)
        self.assertNotIn("update_cells", self.source)
        self.assertNotIn("posted_results --apply", self.source)
        self.assertIn("scripts/recover_orphan_threads_post.py", self.source)
        self.assertIn("sns-growth-production-liver-manager-", self.doc["concurrency"]["group"])


if __name__ == "__main__":
    unittest.main()
