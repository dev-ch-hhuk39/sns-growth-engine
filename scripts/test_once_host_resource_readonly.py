#!/usr/bin/env python3
"""Offline contracts for the one-time, fail-closed SNS host resource audit."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
TARGET = ".github/workflows/sns-once-host-resource-audit.yml"
PATH = ROOT / TARGET


class OneShotHostReadOnlyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATH.read_text(encoding="utf-8")
        cls.data = yaml.safe_load(cls.text)
        cls.job = cls.data["jobs"]["inspect-host"]
        cls.steps = cls.job["steps"]

    def test_first_main_introduction_only(self):
        trigger = self.data.get("on", self.data.get(True))
        self.assertEqual(set(trigger), {"push"})
        self.assertEqual(trigger["push"]["branches"], ["main"])
        self.assertEqual(trigger["push"]["paths"], [TARGET])
        self.assertIn("github.ref == 'refs/heads/main'", self.job["if"])
        guard = self.steps[1]["run"]
        for required in (
            'test "$GITHUB_RUN_ATTEMPT" = "1"',
            'git cat-file -e "$BEFORE_SHA^{commit}"',
            'git cat-file -e "$BEFORE_SHA:$TARGET_WORKFLOW"',
            'git cat-file -e "$GITHUB_SHA:$TARGET_WORKFLOW"',
            'ONE_SHOT_REPLAY_BLOCKED',
        ):
            self.assertIn(required, guard)

    def test_runner_permissions_and_guarded_scope(self):
        self.assertEqual(self.job["runs-on"], ["self-hosted", "Linux", "X64"])
        self.assertEqual(self.job["environment"], "production")
        self.assertEqual(self.data["permissions"], {"contents": "read"})
        self.assertFalse(self.data["concurrency"]["cancel-in-progress"])
        self.assertEqual(self.steps[0]["with"]["fetch-depth"], 2)
        self.assertFalse(self.steps[0]["with"]["persist-credentials"])

    def test_no_sns_or_cloud_external_actions(self):
        for flag in (
            "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
            "ALLOW_MEDIA_POSTS", "ALLOW_REAL_THREADS_VIDEO_POST",
            "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT",
            "ALLOW_CLOUDINARY_UPLOAD", "ALLOW_TRANSCRIPTION_API",
        ):
            self.assertEqual(self.data["env"][flag], "false")
        audit = self.steps[2]["run"]
        for forbidden in ("rm -", "sudo rm", "git push", "gh secret", "curl ",
                          "wget ", "scp ", "ssh ", "docker ", "crontab -",
                          "--confirm-deploy", "--apply", "--confirm-real-post",
                          "bash scripts/deploy_buffered", "publish_threads_post",
                          "process_threads_queue.py", "printenv", "cat $envfile"):
            self.assertNotIn(forbidden, audit)
        self.assertIn("SNS_PUBLISH_ATTEMPTS=0", audit)

    def test_required_readonly_resource_observations(self):
        audit = self.steps[2]["run"]
        for marker in (
            "df -B1 --output=avail /",
            "MemAvailable:",
            "9 * 1024 * 1024 * 1024",
            "384 * 1024",
            "/usr/local/sbin/chadult-vps-resource-check --preflight 9",
            "HOST_STAGE_9GIB_CAPACITY=BLOCKED",
            "HOST_PRIVILEGED_RESOURCE_GATE=BLOCKED_OR_UNAVAILABLE",
        ):
            self.assertIn(marker, audit)

    def test_release_identity_and_runtime_secrecy(self):
        audit = self.steps[2]["run"]
        for marker in (
            "current previous pending", "releases_real=",
            "^[a-f0-9]{40}$", "HOST_RELEASE_POINTERS=UNVERIFIED",
            "HOST_CURRENT_VENV=BLOCKED", "HOST_RUNTIME_ENV_MODE=OWNER_ONLY",
            "HOST_BACKUP_RESTORE_PROOF=NOT_CHECKED",
            "HOST_DEPLOYMENT_AUTHORIZATION=NOT_GRANTED_BY_READONLY_AUDIT",
        ):
            self.assertIn(marker, audit)
        self.assertNotIn('cat "$envfile"', audit)
        self.assertNotIn('source "$envfile"', audit)

    def test_registered_as_canonical_and_protected_host_workflow(self):
        registry = json.loads((ROOT / "config/reference_first_completion.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["workflow_classification"]["canonical"].count(PATH.name), 1)
        testfile = (ROOT / "scripts/test_production_workflows_self_hosted.py").read_text(encoding="utf-8")
        self.assertIn('"sns-once-host-resource-audit.yml"', testfile)


if __name__ == "__main__":
    unittest.main()
