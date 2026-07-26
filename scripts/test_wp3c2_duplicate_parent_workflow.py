import unittest
import os
import yaml

class TestWP3C2DuplicateWorkflow(unittest.TestCase):
    def setUp(self):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".github", "workflows", "wp3c2-duplicate-parent-inspection.yml")
        with open(path, "r") as f:
            self.w = yaml.safe_load(f)
        
        self.on_val = self.w.get("on") if "on" in self.w else self.w.get(True)
        self.job = self.w["jobs"]["inspect_duplicate"]
        self.step_run = ""
        for step in self.job["steps"]:
            if "run" in step and "inspect_wp3c_duplicate_parent.py" in step["run"]:
                self.step_run = step["run"]

    def test_01_workflow_dispatch_only(self):
        self.assertIn("workflow_dispatch", self.on_val)
        
    def test_02_no_schedule(self):
        self.assertNotIn("schedule", self.on_val)
        
    def test_03_permissions(self):
        self.assertEqual(self.w["permissions"]["contents"], "read")
        
    def test_04_production(self):
        self.assertEqual(self.job["environment"], "production")
        
    def test_05_python_311(self):
        found = False
        for step in self.job["steps"]:
            if "uses" in step and "setup-python" in step["uses"]:
                self.assertEqual(step["with"]["python-version"], "3.11")
                found = True
        self.assertTrue(found)
        
    def test_06_concurrency_fixed(self):
        self.assertEqual(self.w["concurrency"]["group"], "sns-growth-wp3c2-duplicate-parent-inspection")
        
    def test_07_cancel_in_progress(self):
        self.assertFalse(self.w["concurrency"]["cancel-in-progress"])
        
    def test_08_nine_safety_flags_false(self):
        flags = [
            "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
            "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT", "ALLOW_CLOUDINARY_UPLOAD",
            "ALLOW_MEDIA_POSTS", "ALLOW_REAL_THREADS_VIDEO_POST", "ALLOW_TRANSCRIPTION_API"
        ]
        for f in flags:
            self.assertEqual(str(self.w["env"][f]).lower(), "false")
            
    def test_09_sheets_credential_only(self):
        expected_keys = {"GCP_SA_JSON_BASE64", "SA_JSON_BASE64", "SPREADSHEET_ID", "SNS_MASTER_SHEET_ID"}
        actual_keys = set(self.job["env"].keys())
        self.assertEqual(expected_keys, actual_keys)
        
    def test_10_no_threads_secret(self):
        for k in self.job["env"].keys():
            self.assertNotIn("THREADS", k)
            
    def test_11_no_cloudinary_secret(self):
        for k in self.job["env"].keys():
            self.assertNotIn("CLOUDINARY", k)
            
    def test_12_no_x_secret(self):
        for k in self.job["env"].keys():
            self.assertNotIn("TWITTER", k)
            self.assertNotIn("X_API", k)
            
    def test_13_no_artifact_upload(self):
        for step in self.job["steps"]:
            if "uses" in step:
                self.assertNotIn("upload-artifact", step["uses"])
                
    def test_14_no_publisher(self):
        self.assertNotIn("publisher", self.step_run)
        
    def test_15_no_source_fetch(self):
        self.assertNotIn("fetch", self.step_run)
        
    def test_16_no_media(self):
        self.assertNotIn("media", self.step_run.split("python3")[0])
        
    def test_17_no_modifying_args(self):
        self.assertNotIn("--apply", self.step_run)
        self.assertNotIn("--delete", self.step_run)
        self.assertNotIn("--update", self.step_run)
        self.assertNotIn("--repair", self.step_run)
        
    def test_18_safe_prefix_exact_1(self):
        self.assertIn("LINE_COUNT=$(grep -c '^WP3C2_SAFE_DUPLICATE_INSPECTION_JSON='", self.step_run)
        self.assertIn('[ "$LINE_COUNT" -ne 1 ]', self.step_run)
        
    def test_19_safe_prefix_zero_lines_fails(self):
        import subprocess
        import textwrap
        
        script = textwrap.dedent('''
        set -e
        echo "some garbage" > /tmp/wp3c2_stdout.log
        LINE_COUNT=$(grep -c '^WP3C2_SAFE_DUPLICATE_INSPECTION_JSON=' /tmp/wp3c2_stdout.log || true)
        if [ "$LINE_COUNT" -ne 1 ]; then
           exit 42
        fi
        ''')
        p = subprocess.run(["bash", "-c", script], capture_output=True)
        self.assertEqual(p.returncode, 42)
        
    def test_20_safe_prefix_two_lines_fails(self):
        import subprocess
        import textwrap
        
        script2 = textwrap.dedent('''
        set -e
        echo "WP3C2_SAFE_DUPLICATE_INSPECTION_JSON={}" > /tmp/wp3c2_stdout.log
        echo "WP3C2_SAFE_DUPLICATE_INSPECTION_JSON={}" >> /tmp/wp3c2_stdout.log
        LINE_COUNT=$(grep -c '^WP3C2_SAFE_DUPLICATE_INSPECTION_JSON=' /tmp/wp3c2_stdout.log || true)
        if [ "$LINE_COUNT" -ne 1 ]; then
           exit 42
        fi
        ''')
        p = subprocess.run(["bash", "-c", script2], capture_output=True)
        self.assertEqual(p.returncode, 42)
        
        script2 = textwrap.dedent('''
        set -e
        echo "WP3C2_SAFE_DUPLICATE_INSPECTION_JSON={}" > /tmp/wp3c2_stdout.log
        echo "WP3C2_SAFE_DUPLICATE_INSPECTION_JSON={}" >> /tmp/wp3c2_stdout.log
        LINE_COUNT=$(grep -c '^WP3C2_SAFE_DUPLICATE_INSPECTION_JSON=' /tmp/wp3c2_stdout.log || true)
        if [ "$LINE_COUNT" -ne 1 ]; then
           exit 42
        fi
        ''')
        p = subprocess.run(["bash", "-c", script2], capture_output=True)
        self.assertEqual(p.returncode, 42)

    def test_21_malformed_json_fail(self):
        import subprocess
        import textwrap
        script = textwrap.dedent('''
        set -e
        echo "WP3C2_SAFE_DUPLICATE_INSPECTION_JSON={bad" > /tmp/wp3c2_stdout.log
        LINE_COUNT=1
        PLAN_LINE=$(grep '^WP3C2_SAFE_DUPLICATE_INSPECTION_JSON=' /tmp/wp3c2_stdout.log)
        PLAN_JSON=${PLAN_LINE#WP3C2_SAFE_DUPLICATE_INSPECTION_JSON=}
        if ! echo "$PLAN_JSON" | jq . > /dev/null 2>&1; then
           exit 43
        fi
        ''')
        p = subprocess.run(["bash", "-c", script], capture_output=True)
        self.assertEqual(p.returncode, 43)

    def test_22_inspector_exit_1(self):
        import subprocess
        import textwrap
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False) as f:
            summary_path = f.name
            
        script = textwrap.dedent('''
        set -e
        INSPECT_EXIT=1
        GITHUB_STEP_SUMMARY="{}"
        
        JSON_VAL='{"overall_status": "FAIL", "sheets_verifier": {"passed": 0, "total": 0, "total_basis": ""}, "target_source_post_id": "target", "parent_candidate_count": 0, "parent_candidates": [], "child_summary": {"child_count": 0, "unique_child_id_count": 0, "duplicate_media_indexes": []}, "recommended_keep_sheet_row_number": null, "manual_delete_candidate_sheet_row_numbers": []}'
        
        echo "WP3C2_SAFE_DUPLICATE_INSPECTION_JSON=$JSON_VAL" > /tmp/wp3c2_stdout.log
        LINE_COUNT=$(grep -c '^WP3C2_SAFE_DUPLICATE_INSPECTION_JSON=' /tmp/wp3c2_stdout.log || true)
        if [ "$LINE_COUNT" -ne 1 ]; then
            echo "Safe inspection JSON prefix must appear exactly once in stdout. Found $LINE_COUNT times." >> "$GITHUB_STEP_SUMMARY"
            exit 1
        fi
        
        PLAN_LINE=$(grep '^WP3C2_SAFE_DUPLICATE_INSPECTION_JSON=' /tmp/wp3c2_stdout.log)
        PLAN_JSON=${PLAN_LINE#WP3C2_SAFE_DUPLICATE_INSPECTION_JSON=}
        if ! echo "$PLAN_JSON" | jq . > /dev/null 2>&1; then
            echo "Inspection returned invalid JSON." >> "$GITHUB_STEP_SUMMARY"
            exit 1
        fi
        
        echo "### Inspection Result" >> "$GITHUB_STEP_SUMMARY"
        echo "- **Overall Status**: $(echo "$PLAN_JSON" | jq -r '.overall_status')" >> "$GITHUB_STEP_SUMMARY"
        echo "- **Target Source Post ID**: $(echo "$PLAN_JSON" | jq -r '.target_source_post_id')" >> "$GITHUB_STEP_SUMMARY"
        echo "#### Sheets Verifier" >> "$GITHUB_STEP_SUMMARY"
        echo "#### Candidates" >> "$GITHUB_STEP_SUMMARY"
        echo "#### Child Summary" >> "$GITHUB_STEP_SUMMARY"
        echo "#### Decision" >> "$GITHUB_STEP_SUMMARY"
        
        exit "$INSPECT_EXIT"
        ''').format(summary_path)
        
        p = subprocess.run(["bash", "-c", script], capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertFalse(p.stderr)
        
        with open(summary_path, 'r') as f:
            summary_content = f.read()
        self.assertIn("FAIL", summary_content)
        self.assertIn("Sheets Verifier", summary_content)
        self.assertIn("Child Summary", summary_content)
        self.assertIn("Decision", summary_content)
        
        if os.path.exists(summary_path):
            os.remove(summary_path)
        
    def test_23_no_full_output_cat(self):
        self.assertNotIn("cat /tmp/wp3c2_inspect.json", self.step_run)
        
    def test_24_no_raw_log_cat(self):
        self.assertNotIn("cat /tmp/wp3c2_stdout.log", self.step_run)
        
    def test_25_no_canonical_hash_value(self):
        self.assertNotIn("\(.canonical_identity_hash)\n", self.step_run)
        
    def test_26_canonical_hash_presence(self):
        self.assertIn(r'Has Canonical Identity Hash: \(if (.canonical_identity_hash // "") != "" then true else false end)', self.step_run)
        
    def test_27_parent_hash_presence(self):
        self.assertIn(r'Has Parent Precondition Hash: \(if (.parent_precondition_hash // "") != "" then true else false end)', self.step_run)
        
    def test_28_row_number(self):
        self.assertIn("Row \(.sheet_row_number)", self.step_run)
        
    def test_29_disposition(self):
        self.assertIn("Disposition: \(.recommended_disposition)", self.step_run)
        
    def test_30_blocker_code(self):
        self.assertIn('Blockers: \((.blocker_codes // []) | join(\", \"))', self.step_run)
        
    def test_31_recommended_keep_row(self):
        self.assertIn('Recommended Keep Row: \($(echo \"$PLAN_JSON\" | jq -r \'.recommended_keep_sheet_row_number\')\)', self.step_run)
        
    def test_32_manual_delete_rows(self):
        self.assertIn('Manual Delete Rows: $(echo \"$PLAN_JSON\" | jq -r \'(.manual_delete_candidate_sheet_row_numbers // []) | join(\", \")\')', self.step_run)