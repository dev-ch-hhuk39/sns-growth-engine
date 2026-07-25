import unittest
import yaml
import os

class TestWP3CRepairPlanWorkflow(unittest.TestCase):
    def setUp(self):
        self.workflow_path = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "wp3c-production-repair-plan.yml")
        with open(self.workflow_path, "r") as f:
            self.workflow = yaml.safe_load(f)

    def test_workflow_dispatch_only(self):
        on_val = self.workflow.get(True, self.workflow.get("on", {}))
        self.assertIn("workflow_dispatch", on_val)
        self.assertEqual(len(on_val), 1)

    def test_permissions(self):
        perms = self.workflow.get("permissions", {})
        self.assertEqual(perms.get("contents"), "read")

    def test_environment(self):
        job = self.workflow["jobs"]["repair_plan"]
        self.assertEqual(job.get("environment"), "production")

    def test_safety_flags(self):
        env = self.workflow.get("env", {})
        self.assertEqual(env.get("PUBLISH_ENABLED"), "false")
        self.assertEqual(env.get("ALLOW_REAL_THREADS_POST"), "false")
        self.assertEqual(env.get("ALLOW_REAL_X_POST"), "false")
        self.assertEqual(env.get("ALLOW_VIDEO_DOWNLOAD"), "false")
        self.assertEqual(env.get("ALLOW_VIDEO_CUT"), "false")
        self.assertEqual(env.get("ALLOW_CLOUDINARY_UPLOAD"), "false")
        self.assertEqual(env.get("ALLOW_MEDIA_POSTS"), "false")
        self.assertEqual(env.get("ALLOW_REAL_THREADS_VIDEO_POST"), "false")
        self.assertEqual(env.get("ALLOW_TRANSCRIPTION_API"), "false")

    def test_secrets(self):
        job = self.workflow["jobs"]["repair_plan"]
        env = job.get("env", {})
        env_str = str(env)
        self.assertNotIn("THREADS_ACCESS_TOKEN", env_str)
        self.assertNotIn("CLOUDINARY", env_str)
        self.assertNotIn("X_API", env_str)

    def test_no_apply(self):
        job = self.workflow["jobs"]["repair_plan"]
        steps = job.get("steps", [])
        for step in steps:
            run = step.get("run", "")
            if "plan_wp3c_production_repairs.py" in run:
                self.assertNotIn("--apply", run)

    def test_no_artifacts(self):
        job = self.workflow["jobs"]["repair_plan"]
        steps = job.get("steps", [])
        for step in steps:
            self.assertNotEqual(step.get("uses", ""), "actions/upload-artifact@v4")

if __name__ == '__main__':
    unittest.main()
