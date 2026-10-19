#!/usr/bin/env python3
"""Operational gate contracts: fail-fast AUTO_READY and read-only root audit."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
AUTOREADY = ROOT / ".github/workflows/autopilot-auto-ready.yml"
AUDIT = ROOT / ".github/workflows/sns-once-host-authority-probe.yml"


class OperationalGateWorkflowTests(unittest.TestCase):
    def test_autonomous_text_isolation_gate_precedes_any_external_work(self):
        source = AUTOREADY.read_text(encoding="utf-8")
        job = yaml.safe_load(source)["jobs"]["auto-ready"]
        names = [step.get("name", "") for step in job["steps"]]
        guard = "Verify isolated legacy text AUTO_READY and preserve V2 draft-only"
        self.assertIn(guard, names)
        self.assertLess(names.index("Resolve scheduled inventory maintenance"), names.index(guard))
        for late in ("Install dependencies", "Guard account and Sheets secrets",
                     "Verify Sheets before AUTO_READY", "Maintain next text-slot READY inventory",
                     "AUTO_READY apply only"):
            self.assertLess(names.index(guard), names.index(late))
        step = next(item for item in job["steps"] if item.get("name") == guard)
        self.assertEqual(step["if"], "env.AUTO_READY_APPLY == 'true'")
        self.assertIn("python3 scripts/auto_ready_draft_preflight.py --autonomous-text-only", step["run"])
        self.assertIn('--account-id "$ACCOUNT_ID"', step["run"])
        self.assertEqual(job["runs-on"], "ubuntu-latest")
        for flag in ("PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST"):
            self.assertEqual(yaml.safe_load(source)["env"][flag], "false")
        self.assertNotIn("--confirm-real-post", source)

    def test_one_shot_vps_authority_audit_has_no_writes_or_privilege_escalation(self):
        source = AUDIT.read_text(encoding="utf-8")
        doc = yaml.safe_load(source)
        trigger = doc.get("on", doc.get(True))
        self.assertEqual(set(trigger), {"push"})
        self.assertEqual(trigger["push"]["branches"], ["main"])
        self.assertEqual(trigger["push"]["paths"], [".github/workflows/sns-once-host-authority-probe.yml"])
        self.assertEqual(doc["permissions"], {"contents": "read"})
        job = doc["jobs"]["audit-only"]
        self.assertEqual(job["runs-on"], ["self-hosted", "Linux", "X64"])
        self.assertEqual(job["environment"], "production")
        self.assertFalse(doc["concurrency"]["cancel-in-progress"])
        self.assertFalse(job["steps"][0]["with"]["persist-credentials"])
        guard = job["steps"][1]["run"]
        for marker in ('test "$GITHUB_RUN_ATTEMPT" = 1',
                       'git cat-file -e "$BEFORE_SHA:$TARGET_WORKFLOW"',
                       'git cat-file -e "$GITHUB_SHA:$TARGET_WORKFLOW"'):
            self.assertIn(marker, guard)
        audit = job["steps"][2]["run"]
        self.assertIn("python3 scripts/sns_vps_authority_capability.py", audit)
        for banned in ("--apply", "--confirm", "sudo -n python", "sudo rm", "rm -rf",
                       "docker ", "crontab ", "curl ", "gh secret", "ssh ",
                       "--confirm-real-post", "deploy_buffered"):
            self.assertNotIn(banned, audit)
        self.assertIn("SNS_PUBLISH_ATTEMPTS=0", audit)
        for flag in ("PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
                     "ALLOW_MEDIA_POSTS", "ALLOW_REAL_THREADS_VIDEO_POST",
                     "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT",
                     "ALLOW_CLOUDINARY_UPLOAD", "ALLOW_TRANSCRIPTION_API"):
            self.assertEqual(doc["env"][flag], "false")

    def test_inventory_and_runner_allowlist_register_new_workflow(self):
        data = json.loads((ROOT / "config/reference_first_completion.json").read_text(encoding="utf-8"))
        self.assertEqual(data["workflow_classification"]["canonical"].count(AUDIT.name), 1)
        hostlist = (ROOT / "scripts/test_production_workflows_self_hosted.py").read_text(encoding="utf-8")
        self.assertIn('"' + AUDIT.name + '"', hostlist)


if __name__ == "__main__":
    unittest.main()
