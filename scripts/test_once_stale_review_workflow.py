#!/usr/bin/env python3
"""One immutable stale review concurrency recovery: workflow contract."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/sns-once-review-concurrency-relief.yml"


class OnceStaleReviewContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = WORKFLOW.read_text(encoding="utf-8")
        cls.doc = yaml.safe_load(cls.source)
        cls.job = cls.doc["jobs"]["cancel-exact-stale-review"]
        cls.steps = cls.job["steps"]

    def test_main_introduction_only_no_dispatch_or_schedule(self):
        triggers = self.doc.get("on", self.doc.get(True))
        self.assertEqual(set(triggers), {"push"})
        self.assertEqual(triggers["push"]["branches"], ["main"])
        self.assertEqual(triggers["push"]["paths"], [
            ".github/workflows/sns-once-review-concurrency-relief.yml"
        ])
        self.assertEqual(self.doc["permissions"], {"contents": "read"})
        self.assertFalse(self.doc["concurrency"]["cancel-in-progress"])
        self.assertEqual(self.job["runs-on"], "ubuntu-latest")
        self.assertEqual(self.job["permissions"], {"contents": "read", "actions": "write"})
        self.assertEqual(self.steps[0]["with"]["fetch-depth"], 2)
        self.assertFalse(self.steps[0]["with"]["persist-credentials"])

    def test_one_shot_guard_and_tightly_scoped_cancel(self):
        guard = self.steps[1]["run"]
        for marker in (
            'test "$GITHUB_RUN_ATTEMPT" = 1',
            'git cat-file -e "$BEFORE_SHA^{commit}"',
            'git cat-file -e "$BEFORE_SHA:$TARGET_WORKFLOW"',
            'git cat-file -e "$GITHUB_SHA:$TARGET_WORKFLOW"',
            "ONE_SHOT_REPLAY_BLOCKED",
        ):
            self.assertIn(marker, guard)
        step = self.steps[2]
        self.assertEqual(step["env"]["SNS_EXACT_STALE_REVIEW_ALLOWED"], "true")
        self.assertIn("python3 scripts/cancel_exact_stale_review_once.py", step["run"])
        self.assertIn("SNS_QUEUE_OR_SHEETS_WRITES=0", step["run"])
        script = (ROOT / "scripts/cancel_exact_stale_review_once.py").read_text(encoding="utf-8")
        for item in (
            "RUN_ID = 37327934561",
            "JOB_ID = 111823333981",
            "EXPECTED_CREATED =",
            "EXPECTED_JOB_STARTED =",
            "head_sha",
            "runner_name",
            "steps",
            "run_attempt",
        ):
            self.assertIn(item, script)

    def test_no_real_actions_or_database_mutations(self):
        for flag in (
            "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
            "ALLOW_MEDIA_POSTS", "ALLOW_REAL_THREADS_VIDEO_POST",
            "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT",
            "ALLOW_CLOUDINARY_UPLOAD", "ALLOW_TRANSCRIPTION_API",
        ):
            self.assertEqual(self.doc["env"][flag], "false")
        for token in (
            "--confirm-real-post", "publish_threads_post",
            "process_threads_queue.py", "docker ", "sudo ",
            "gh secret", "curl ", "rm -rf", "git push", "crontab ",
        ):
            self.assertNotIn(token, self.source)
        self.assertIn("SNS_PUBLISH_ATTEMPTS=0", self.source)

    def test_registry_exactly_once(self):
        registry = json.loads((ROOT / "config/reference_first_completion.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["workflow_classification"]["canonical"].count(WORKFLOW.name), 1)


if __name__ == "__main__":
    unittest.main()
