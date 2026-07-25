import unittest
import yaml
import os

class TestWP3CRepairPlanWorkflow(unittest.TestCase):
    def setUp(self):
        self.workflow_path = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "wp3c-production-repair-plan.yml")
        with open(self.workflow_path, "r") as f:
            self.workflow = yaml.safe_load(f)
        with open(self.workflow_path, "r") as f:
            self.workflow_text = f.read()

    def test_01_workflow_dispatch_only(self):
        on_val = self.workflow.get(True, self.workflow.get("on", {}))
        self.assertIn("workflow_dispatch", on_val)
        self.assertEqual(len(on_val), 1)

    def test_02_schedule_not_present(self):
        on_val = self.workflow.get(True, self.workflow.get("on", {}))
        self.assertNotIn("schedule", on_val)

    def test_03_permissions(self):
        perms = self.workflow.get("permissions", {})
        self.assertEqual(perms.get("contents"), "read")

    def test_04_production_environment(self):
        job = self.workflow["jobs"]["repair_plan"]
        self.assertEqual(job.get("environment"), "production")

    def test_05_python_version(self):
        job = self.workflow["jobs"]["repair_plan"]
        for step in job.get("steps", []):
            if step.get("uses", "").startswith("actions/setup-python"):
                self.assertEqual(step.get("with", {}).get("python-version"), "3.11")

    def test_06_concurrency(self):
        conc = self.workflow.get("concurrency", {})
        self.assertEqual(conc.get("group"), "sns-growth-wp3c-repair-plan")
        self.assertEqual(conc.get("cancel-in-progress"), False)

    def test_07_safety_flags_false(self):
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

    def test_08_sheets_credentials_only(self):
        job = self.workflow["jobs"]["repair_plan"]
        env = job.get("env", {})
        self.assertIn("GCP_SA_JSON_BASE64", env)
        self.assertIn("SPREADSHEET_ID", env)

    def test_09_to_11_no_other_secrets(self):
        job = self.workflow["jobs"]["repair_plan"]
        env_str = str(job.get("env", {}))
        self.assertNotIn("THREADS_ACCESS_TOKEN", env_str)
        self.assertNotIn("CLOUDINARY", env_str)
        self.assertNotIn("X_API", env_str)

    def test_12_no_artifact_upload(self):
        self.assertNotIn("actions/upload-artifact", self.workflow_text)

    def test_13_no_full_plan_cat(self):
        self.assertNotIn("cat /tmp/wp3c_repair_plan.json", self.workflow_text)

    def test_14_no_source_fetch(self):
        self.assertNotIn("acquire_approved_source_posts.py", self.workflow_text)

    def test_15_no_publisher(self):
        self.assertNotIn("threads_publisher.py", self.workflow_text)

    def test_16_no_apply_args(self):
        self.assertNotIn("--apply", self.workflow_text)
        self.assertNotIn("--write", self.workflow_text)
        self.assertNotIn("--repair", self.workflow_text)

    def test_17_19_20_safe_line_check(self):
        self.assertIn('LINE_COUNT=$(grep -c \'WP3C_SAFE_REPAIR_PLAN_JSON=\' /tmp/wp3c_stdout.log || true)', self.workflow_text)
        self.assertIn('if [ "$LINE_COUNT" -ne 1 ]; then', self.workflow_text)
        self.assertIn('exit 1', self.workflow_text)

    def test_18_malformed_json_fail(self):
        self.assertIn('echo "$PLAN_JSON" | jq . > /dev/null 2>&1', self.workflow_text)
        
    def test_21_22_planner_exit_code_and_summary(self):
        self.assertIn('PLANNER_EXIT=$?', self.workflow_text)
        self.assertIn('exit "$PLANNER_EXIT"', self.workflow_text)
        self.assertTrue(self.workflow_text.find('GITHUB_STEP_SUMMARY') < self.workflow_text.find('exit "$PLANNER_EXIT"'))

    def test_23_24_duplicate_groups_and_operation_types_in_summary(self):
        self.assertIn('.duplicate_index_groups[]?', self.workflow_text)
        self.assertIn('.operations | map(.operation) | join(", ")', self.workflow_text)

    def test_25_no_echo_secret(self):
        self.assertNotIn('echo "${{ secrets', self.workflow_text)

if __name__ == '__main__':
    unittest.main()
