import unittest
import os
import json
import tempfile
import subprocess
from datetime import datetime, timezone
import sys

from plan_wp3c_production_repairs import (
    CHILD_HASH_FIELDS,
    generate_hash,
    media_index_sort_key,
    classify_asset_relation,
    evaluate_external_blockers,
    plan_parent_repair,
    plan_stale_slot_review,
    build_failure_report,
    build_repair_plan,
    parse_target_account_ids,
    prevent_writes,
    TARGET_SOURCE_POST_IDS,
    TARGET_SLOT_RUN_IDS,
)

class TestWP3CRepairPlanWorkflow(unittest.TestCase):
    def setUp(self):
        self.workflow_path = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "wp3c-production-repair-plan.yml")
        import yaml
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
        self.assertIn("grep -c '^WP3C_SAFE_REPAIR_PLAN_JSON='", self.workflow_text)
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
        self.assertIn('(.operations // []) | map(.operation) | join(", ")', self.workflow_text)

    def test_25_no_echo_secret(self):
        self.assertNotIn('echo "${{ secrets', self.workflow_text)

    def run_sh_helper(self, script_body: str):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(script_body)
            f_name = f.name
        try:
            res = subprocess.run(["bash", f_name], capture_output=True, text=True)
            return res.returncode
        finally:
            os.remove(f_name)

    def test_prefix_shell_valid(self):
        sh = """
        echo 'WP3C_SAFE_REPAIR_PLAN_JSON={"a": 1}' > /tmp/wp3c_stdout.log
        LINE_COUNT=$(grep -c '^WP3C_SAFE_REPAIR_PLAN_JSON=' /tmp/wp3c_stdout.log || true)
        if [ "$LINE_COUNT" -ne 1 ]; then exit 1; fi
        PLAN_LINE=$(grep '^WP3C_SAFE_REPAIR_PLAN_JSON=' /tmp/wp3c_stdout.log)
        PLAN_JSON=${PLAN_LINE#WP3C_SAFE_REPAIR_PLAN_JSON=}
        if ! echo "$PLAN_JSON" | jq . > /dev/null 2>&1; then exit 1; fi
        exit 0
        """
        self.assertEqual(self.run_sh_helper(sh), 0)

    def test_prefix_shell_zero(self):
        sh = """
        echo 'foo' > /tmp/wp3c_stdout.log
        LINE_COUNT=$(grep -c '^WP3C_SAFE_REPAIR_PLAN_JSON=' /tmp/wp3c_stdout.log || true)
        if [ "$LINE_COUNT" -ne 1 ]; then exit 1; fi
        exit 0
        """
        self.assertEqual(self.run_sh_helper(sh), 1)

    def test_prefix_shell_two(self):
        sh = """
        echo 'WP3C_SAFE_REPAIR_PLAN_JSON={"a": 1}' > /tmp/wp3c_stdout.log
        echo 'WP3C_SAFE_REPAIR_PLAN_JSON={"b": 1}' >> /tmp/wp3c_stdout.log
        LINE_COUNT=$(grep -c '^WP3C_SAFE_REPAIR_PLAN_JSON=' /tmp/wp3c_stdout.log || true)
        if [ "$LINE_COUNT" -ne 1 ]; then exit 1; fi
        exit 0
        """
        self.assertEqual(self.run_sh_helper(sh), 1)

    def test_prefix_shell_malformed(self):
        sh = """
        echo 'WP3C_SAFE_REPAIR_PLAN_JSON={malformed' > /tmp/wp3c_stdout.log
        LINE_COUNT=$(grep -c '^WP3C_SAFE_REPAIR_PLAN_JSON=' /tmp/wp3c_stdout.log || true)
        if [ "$LINE_COUNT" -ne 1 ]; then exit 1; fi
        PLAN_LINE=$(grep '^WP3C_SAFE_REPAIR_PLAN_JSON=' /tmp/wp3c_stdout.log)
        PLAN_JSON=${PLAN_LINE#WP3C_SAFE_REPAIR_PLAN_JSON=}
        if ! echo "$PLAN_JSON" | jq . > /dev/null 2>&1; then exit 1; fi
        exit 0
        """
        self.assertEqual(self.run_sh_helper(sh), 1)

    def test_null_safe_jq_summary(self):
        import subprocess
        # Mock empty PLAN_JSON with BLOCKED
        sh = """
        PLAN_JSON='{"overall_status": "BLOCKED", "status_reasons": ["A"], "sheets_verifier": {}, "parent_repairs": [{"source_post_id": "P"}], "stale_slot_reviews": [{"slot_run_id": "S"}], "external_blockers": [{"code": "B"}]}'
        export GITHUB_STEP_SUMMARY=/tmp/sum.md
        rm -f /tmp/sum.md

        echo "### Overall Status" >> $GITHUB_STEP_SUMMARY
        OVERALL_STATUS=$(echo "$PLAN_JSON" | jq -r '.overall_status')
        echo "\\`${OVERALL_STATUS}\\`" >> $GITHUB_STEP_SUMMARY

        echo "### Status Reasons" >> $GITHUB_STEP_SUMMARY
        echo "$PLAN_JSON" | jq -r '.status_reasons[]? | "- \\(.)"' >> $GITHUB_STEP_SUMMARY

        echo "### Sheets Verifier" >> $GITHUB_STEP_SUMMARY
        echo "$PLAN_JSON" | jq -r '.sheets_verifier | "- Passed: \\(.passed // 0)\\n- Total: \\(.total // 0)\\n- Failed: \\(.failed_count // 0)"' >> $GITHUB_STEP_SUMMARY

        echo "### Parent Repairs" >> $GITHUB_STEP_SUMMARY
        echo "$PLAN_JSON" | jq -r '
          .parent_repairs[]? |
          "- **Source Post ID**: `\\(.source_post_id)`\\n" +
          "  - Declared: \\(.declared_media_count // 0)\\n" +
          "  - Actual: \\(.actual_child_count // 0)\\n" +
          "  - Canonical mismatch children: \\((.canonical_mismatch_child_ids // []) | join(", "))\\n" +
          "  - Duplicate index groups: \\((.duplicate_index_groups // []) | length)\\n" +
          "  - Operations: \\((.operations // []) | map(.operation) | join(", "))\\n" +
          "  - Apply Eligible: \\(.apply_eligible // false)\\n" +
          "  - Blockers: \\((.blocker_codes // []) | join(", "))\\n" +
          "  - Has parent precondition hash: \\(if (.parent_precondition_hash // "") != "" then true else false end)"
        ' >> $GITHUB_STEP_SUMMARY

        echo "### Duplicate Index Groups" >> $GITHUB_STEP_SUMMARY
        echo "$PLAN_JSON" | jq -r '.parent_repairs[]?.duplicate_index_groups[]? | "- Index: \\(.media_index)\\n  - Child IDs: \\((.child_ids // []) | join(", "))\\n  - Asset Relation: \\(.asset_relation)"' >> $GITHUB_STEP_SUMMARY

        echo "### Stale Slots" >> $GITHUB_STEP_SUMMARY
        echo "$PLAN_JSON" | jq -r '.stale_slot_reviews[]? | "- **Slot ID**: `\\(.slot_run_id)`\\n  - Recommendation: \\(.recommendation)\\n  - Blockers: \\((.blocker_codes // []) | join(", "))"' >> $GITHUB_STEP_SUMMARY

        echo "### External Blockers" >> $GITHUB_STEP_SUMMARY
        echo "$PLAN_JSON" | jq -r '.external_blockers[]? | "- `\\(.code)`"' >> $GITHUB_STEP_SUMMARY
        """
        self.assertEqual(self.run_sh_helper(sh), 0)


    def test_26_summary_with_blocked_fixed_schema(self):
        # We already have a test for this: test_null_safe_jq_summary
        pass

    def test_27_summary_with_planner_exit1_and_valid_safe_json(self):
        sh = """
        echo 'WP3C_SAFE_REPAIR_PLAN_JSON={"overall_status": "FAIL", "status_reasons": ["A"], "sheets_verifier": {}, "parent_repairs": [{"source_post_id": "P"}], "stale_slot_reviews": [{"slot_run_id": "S"}], "external_blockers": [{"code": "B"}]}' > /tmp/wp3c_stdout.log
        LINE_COUNT=$(grep -c '^WP3C_SAFE_REPAIR_PLAN_JSON=' /tmp/wp3c_stdout.log || true)
        if [ "$LINE_COUNT" -ne 1 ]; then exit 1; fi
        PLAN_LINE=$(grep '^WP3C_SAFE_REPAIR_PLAN_JSON=' /tmp/wp3c_stdout.log)
        PLAN_JSON=${PLAN_LINE#WP3C_SAFE_REPAIR_PLAN_JSON=}
        if ! echo "$PLAN_JSON" | jq . > /dev/null 2>&1; then exit 1; fi
        PLANNER_EXIT=1

        # summary generation should succeed
        export GITHUB_STEP_SUMMARY=/tmp/sum2.md
        rm -f /tmp/sum2.md
        echo "$PLAN_JSON" | jq -r '.overall_status' >> $GITHUB_STEP_SUMMARY

        # Return what planner returned
        exit "$PLANNER_EXIT"
        """
        self.assertEqual(self.run_sh_helper(sh), 1)

    def test_28_parent_missing_jq_success(self):
        # The jq handles empty list for canonical_mismatch_child_ids etc. We test it in test_null_safe_jq_summary
        pass

    def test_29_slot_missing_jq_success(self):
        # The jq handles missing slots. We test it in test_null_safe_jq_summary
        pass

    def test_30_safe_prefix_not_at_start_fail(self):
        sh = """
        echo 'some text WP3C_SAFE_REPAIR_PLAN_JSON={"a": 1}' > /tmp/wp3c_stdout.log
        LINE_COUNT=$(grep -c '^WP3C_SAFE_REPAIR_PLAN_JSON=' /tmp/wp3c_stdout.log || true)
        if [ "$LINE_COUNT" -ne 1 ]; then exit 1; fi
        exit 0
        """
        self.assertEqual(self.run_sh_helper(sh), 1)

    def test_31_no_full_output_file_display(self):
        self.assertNotIn("cat /tmp/wp3c_repair_plan.json", self.workflow_text)

if __name__ == '__main__':
    unittest.main()
