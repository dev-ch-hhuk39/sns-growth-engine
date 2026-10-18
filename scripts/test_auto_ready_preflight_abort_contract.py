#!/usr/bin/env python3
"""A failed production verification must block every subsequent Sheets writer."""
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/autopilot-auto-ready.yml"


class AutoReadyAbortContract(unittest.TestCase):
    def setUp(self):
        doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        self.steps = doc["jobs"]["auto-ready"]["steps"]

    def test_emergency_bank_not_run_after_failed_verify(self):
        refill = next(step for step in self.steps
                      if step.get("name") == "Refill validated non-AI emergency bank")
        self.assertIn("success()", str(refill["if"]))
        self.assertNotIn("always()", str(refill["if"]))
        self.assertIn("steps.preparation_guard.outcome == 'success'", str(refill["if"]))

    def test_verify_happens_before_any_ready_writes(self):
        names = [step.get("name") for step in self.steps]
        verify = names.index("Verify Sheets before AUTO_READY")
        for name in ("Maintain next text-slot READY inventory",
                     "Refill validated non-AI emergency bank",
                     "AUTO_READY apply only"):
            self.assertLess(verify, names.index(name))
        self.assertIn("--verify-only --text-inventory-scope",
                      str(self.steps[verify]["run"]))

    def test_posting_disabled_in_workflow(self):
        doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
        env = doc["env"]
        self.assertEqual(env["PUBLISH_ENABLED"], "false")
        self.assertEqual(env["ALLOW_REAL_THREADS_POST"], "false")
        self.assertEqual(env["ALLOW_REAL_X_POST"], "false")
        apply = next(step for step in self.steps if step.get("name") == "AUTO_READY apply only")
        self.assertIn("--skip-real-post", apply["run"])


if __name__ == "__main__":
    unittest.main()
