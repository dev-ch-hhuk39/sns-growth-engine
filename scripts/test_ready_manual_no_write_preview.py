#!/usr/bin/env python3
"""Manual unconfirmed AUTO_READY dispatch executes genuine read-only verification."""
from __future__ import annotations
import unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
WORKFLOW=ROOT/".github/workflows/autopilot-auto-ready.yml"

class ManualReadyNoWriteContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        doc=yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        cls.steps={s["name"]:s for s in doc["jobs"]["auto-ready"]["steps"] if "name" in s}
        cls.ordered=[s["name"] for s in doc["jobs"]["auto-ready"]["steps"] if "name" in s]
        cls.env=doc["env"]

    def test_preview_runs_without_auto_ready_confirmation(self):
        setup=self.steps["Resolve scheduled inventory maintenance"]["run"]
        self.assertIn("apply=false",setup)
        step=self.steps["Preview exact-slot READY with no Sheets writes"]
        self.assertIn("github.event_name == 'workflow_dispatch'",step["if"])
        self.assertIn("env.AUTO_READY_APPLY != 'true'",step["if"])
        self.assertLess(self.ordered.index("Install dependencies"),
                        self.ordered.index("Preview exact-slot READY with no Sheets writes"))
        self.assertIn("github.event_name == 'workflow_dispatch'",
                      self.steps["Install dependencies"]["if"])

    def test_preview_cannot_write_or_publish(self):
        script=self.steps["Preview exact-slot READY with no Sheets writes"]["run"]
        self.assertIn('> "$ready_report" 2> "$ready_stderr"',script)
        self.assertIn("--dry-run --use-sheets",script)
        self.assertIn("ready_inventory_diagnostics.py",script)
        self.assertIn("exit 1",script)
        for unsafe in ("--apply","--confirm-real-post","--confirm-ready-maintenance",
                       "--auto-post","process_threads_queue.py"):
            self.assertNotIn(unsafe,script)

    def test_existing_publish_guards_remain_off(self):
        for flag in ("PUBLISH_ENABLED","ALLOW_REAL_THREADS_POST","ALLOW_REAL_X_POST"):
            self.assertEqual(self.env[flag],"false")
        verify=self.steps["Verify Sheets before AUTO_READY"]
        self.assertEqual(verify["if"],"env.AUTO_READY_APPLY == 'true'")
        self.assertLess(self.ordered.index("Verify Sheets before AUTO_READY"),
                        self.ordered.index("Maintain next text-slot READY inventory"))
        self.assertIn("--skip-real-post",self.steps["AUTO_READY apply only"]["run"])

if __name__=="__main__":
    unittest.main()
