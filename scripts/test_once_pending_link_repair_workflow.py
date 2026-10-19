#!/usr/bin/env python3
"""Offline guard for one exact abandoned SNS pending-link-only repair."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
FILE = "sns-once-resolve-abandoned-pending.yml"
PATH = ROOT / ".github/workflows" / FILE
EXPECTED = {
    "EXPECTED_CURRENT": "f6b78bacd6fa4a72d67894bd3c09cbac38391d99",
    "EXPECTED_PREVIOUS": "2fd217c5910704cdf3f686f0ebadbc731a33c1fd",
    "EXPECTED_PENDING": "bec16989c859e97abe53a736afb6d76bc12338a1",
}


class OncePendingLinkRepairTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATH.read_text(encoding="utf-8")
        cls.doc = yaml.safe_load(cls.text)
        cls.job = cls.doc["jobs"]["clear-one-abandoned-symlink"]
        cls.steps = cls.job["steps"]

    def test_scope_and_one_shot_guard(self):
        on = self.doc.get("on", self.doc.get(True))
        self.assertEqual(set(on), {"push"})
        self.assertEqual(on["push"]["branches"], ["main"])
        self.assertEqual(on["push"]["paths"], [".github/workflows/" + FILE])
        self.assertEqual(self.job["runs-on"], ["self-hosted", "Linux", "X64"])
        self.assertEqual(self.job["environment"], "production")
        self.assertEqual(self.doc["permissions"], {"contents": "read"})
        self.assertFalse(self.doc["concurrency"]["cancel-in-progress"])
        guard = self.steps[1]["run"]
        for s in (
            'test "$GITHUB_RUN_ATTEMPT" = 1',
            'git cat-file -e "$BEFORE_SHA^{commit}"',
            'git cat-file -e "$BEFORE_SHA:$TARGET_WORKFLOW"',
            'git cat-file -e "$GITHUB_SHA:$TARGET_WORKFLOW"',
        ):
            self.assertIn(s, guard)

    def test_exact_old_current_rollback_and_abandoned_candidate(self):
        self.assertEqual({k: self.job["env"][k] for k in EXPECTED}, EXPECTED)
        self.assertIn('readlink -f "$root/previous"', self.steps[1]["run"])
        self.assertIn('readlink -f "$root/pending"', self.steps[1]["run"])

    def test_readonly_pass_precedes_single_apply(self):
        preview = self.steps[2]["run"]
        apply = self.steps[3]["run"]
        self.assertIn("scripts/resolve_abandoned_sns_pending.py", preview)
        self.assertIn("scripts/resolve_abandoned_sns_pending.py", apply)
        self.assertNotIn("--confirm", preview)
        self.assertIn('"mode": "DRY_RUN"', preview)
        self.assertIn("--confirm CLEAR_EXACT_PENDING_POINTER_ONLY", apply)
        self.assertIn('"removed_only_pending_symlink": true', apply)
        self.assertIn('"mode": "APPLY"', apply)

    def test_never_removes_release_or_enables_posting(self):
        for key in (
            "PUBLISH_ENABLED", "POSTING_ENABLED", "ALLOW_REAL_THREADS_POST",
            "ALLOW_REAL_X_POST", "ALLOW_MEDIA_POSTS",
            "ALLOW_REAL_THREADS_VIDEO_POST", "ALLOW_VIDEO_DOWNLOAD",
            "ALLOW_VIDEO_CUT", "ALLOW_CLOUDINARY_UPLOAD", "ALLOW_TRANSCRIPTION_API",
        ):
            self.assertEqual(self.doc["env"][key], "false")
        for banned in ("rm -rf", "rmdir", "shutil.rmtree", "git push",
                       "gh secret", "curl ", "wget ", "deploy_buffered_runtime",
                       "process_threads_queue.py", "publish_threads_post.py",
                       "posting_enabled: true"):
            self.assertNotIn(banned, self.text)
        self.assertIn('test -d "$root/releases/$EXPECTED_PENDING"', self.text)
        self.assertIn("SNS_PUBLISH_ATTEMPTS=0", self.text)

    def test_existing_trusted_resolver_contains_strict_safety_checks(self):
        script = (ROOT / "scripts/resolve_abandoned_sns_pending.py").read_text(encoding="utf-8")
        for s in (
            "SNS_POSTING_OR_AUTONOMY_ACTIVE",
            "SHARED_DEPLOY_LOCK_UNAVAILABLE",
            "SNS_PENDING_CURRENT_OR_ROLLBACK_PROTECTED",
            "assert_not_in_use",
            '(root / "pending").unlink()',
        ):
            self.assertIn(s, script)

    def test_registered_canonical_and_selfhost_allowlisted(self):
        registry = json.loads((ROOT / "config/reference_first_completion.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["workflow_classification"]["canonical"].count(FILE), 1)
        check = (ROOT / "scripts/test_production_workflows_self_hosted.py").read_text(encoding="utf-8")
        self.assertIn('"' + FILE + '"', check)


if __name__ == "__main__":
    unittest.main()
