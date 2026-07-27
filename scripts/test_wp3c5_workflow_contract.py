#!/usr/bin/env python3
import os
import yaml
import unittest

class TestWP3C5WorkflowContract(unittest.TestCase):
    def setUp(self):
        self.workflow_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            ".github",
            "workflows",
            "wp3c5-safe-youtube-path-provenance.yml"
        )
        with open(self.workflow_path, "r", encoding="utf-8") as f:
            self.workflow = yaml.safe_load(f)

    def test_workflow_name(self):
        self.assertEqual(self.workflow.get("name"), "WP3-C5 Safe YouTube Path Provenance")

    def test_on_workflow_dispatch_only(self):
        self.assertEqual(list(self.workflow[True].keys()), ["workflow_dispatch"])

    def test_permissions(self):
        perms = self.workflow.get("permissions", {})
        self.assertEqual(perms.get("contents"), "read")
        self.assertEqual(len(perms), 1)

    def test_jobs_structure(self):
        jobs = self.workflow.get("jobs", {})
        self.assertIn("inspect", jobs)
        self.assertEqual(len(jobs), 1)

    def test_safety_flags_are_false(self):
        inspect_job = self.workflow["jobs"]["inspect"]
        env = inspect_job.get("steps", [])[3].get("env", {})
        
        self.assertEqual(str(env.get("PUBLISH_ENABLED", "")).lower(), "false")
        self.assertEqual(str(env.get("ALLOW_REAL_THREADS_POST", "")).lower(), "false")
        self.assertEqual(str(env.get("ALLOW_REAL_X_POST", "")).lower(), "false")
        self.assertEqual(str(env.get("ALLOW_VIDEO_DOWNLOAD", "")).lower(), "false")

if __name__ == "__main__":
    unittest.main()
