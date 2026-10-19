#!/usr/bin/env python3
"""Read-only pending diagnosis must not undo an uncertain one-shot write."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
import yaml

import diagnose_abandoned_sns_pending as diag

ROOT = Path(__file__).resolve().parents[1]
NAME = "sns-once-diagnose-pending-access.yml"
FLOW = ROOT / ".github/workflows" / NAME
CURRENT = "f6b78bacd6fa4a72d67894bd3c09cbac38391d99"
PREVIOUS = "2fd217c5910704cdf3f686f0ebadbc731a33c1fd"
PENDING = "bec16989c859e97abe53a736afb6d76bc12338a1"


class PendingDiagnosisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = FLOW.read_text(encoding="utf-8")
        cls.doc = yaml.safe_load(cls.text)
        cls.job = cls.doc["jobs"]["diagnose-only"]
        cls.steps = cls.job["steps"]

    def test_no_mutation_or_external_publishing(self):
        source = (ROOT / "scripts/diagnose_abandoned_sns_pending.py").read_text(encoding="utf-8")
        for banned in (".unlink(", "rmtree(", "os.remove(", "os.replace(",
                       "subprocess.", "requests.", "urllib.", "curl ",
                       "process_threads_queue.py", "--confirm-real-post"):
            self.assertNotIn(banned, source)
        for key in ("PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
                    "ALLOW_MEDIA_POSTS", "ALLOW_REAL_THREADS_VIDEO_POST",
                    "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT",
                    "ALLOW_CLOUDINARY_UPLOAD", "ALLOW_TRANSCRIPTION_API"):
            self.assertEqual(self.doc["env"][key], "false")
        self.assertIn("SNS_PENDING_DIAGNOSIS_MODE=READ_ONLY", self.text)

    def test_strict_first_main_introduction(self):
        on = self.doc.get("on", self.doc.get(True))
        self.assertEqual(set(on), {"push"})
        self.assertEqual(on["push"]["branches"], ["main"])
        self.assertEqual(on["push"]["paths"], [".github/workflows/" + NAME])
        self.assertEqual(self.job["runs-on"], ["self-hosted", "Linux", "X64"])
        self.assertEqual(self.doc["permissions"], {"contents": "read"})
        self.assertEqual(self.job["environment"], "production")
        guard = self.steps[1]["run"]
        self.assertIn('test "$GITHUB_RUN_ATTEMPT" = 1', guard)
        self.assertIn('git cat-file -e "$BEFORE_SHA:$TARGET_WORKFLOW"', guard)

    def test_exact_release_identities_and_redacted_output(self):
        env = self.job["env"]
        self.assertEqual(env["EXPECTED_CURRENT"], CURRENT)
        self.assertEqual(env["EXPECTED_PREVIOUS"], PREVIOUS)
        self.assertEqual(env["EXPECTED_PENDING"], PENDING)
        command = self.steps[2]["run"]
        self.assertIn("scripts/diagnose_abandoned_sns_pending.py", command)
        self.assertNotIn("--confirm", command)
        self.assertIn("SNS_PUBLISH_ATTEMPTS=0", command)
        self.assertIn("PROCESS_INVENTORY_UNREADABLE", str(diag.PROCESS_CATEGORIES.values()))

    def test_invalid_current_blocks_without_mutating(self):
        with tempfile.TemporaryDirectory() as td:
            state = diag.diagnose(CURRENT, PREVIOUS, PENDING, root=Path(td), lock=Path(td) / "lock")
        self.assertEqual(state["status"], "BLOCKED")
        self.assertEqual(state["category"], "CURRENT_OR_ROLLBACK_MISMATCH")
        self.assertFalse(state["would_delete"])
        self.assertFalse(state["would_post"])

    def test_missing_pending_reports_absent_not_repaired(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / ".buffered-runtime"
            releases = base / "releases"
            releases.mkdir(parents=True)
            for role, sha in (("current", CURRENT), ("previous", PREVIOUS)):
                path = releases / sha
                path.mkdir()
                (base / role).symlink_to(path, target_is_directory=True)
            state = diag.diagnose(CURRENT, PREVIOUS, PENDING, root=base, lock=base / "lock")
        self.assertEqual(state["status"], "ALREADY_ABSENT")
        self.assertEqual(state["category"], "NO_PENDING_LINK")
        self.assertFalse(state["would_delete"])

    def test_inventory_registration(self):
        registry = json.loads((ROOT / "config/reference_first_completion.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["workflow_classification"]["canonical"].count(NAME), 1)
        allow = (ROOT / "scripts/test_production_workflows_self_hosted.py").read_text(encoding="utf-8")
        self.assertIn('"' + NAME + '"', allow)


if __name__ == "__main__":
    unittest.main()
