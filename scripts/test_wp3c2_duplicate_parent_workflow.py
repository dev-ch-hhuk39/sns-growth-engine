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
    def test_21_summary_renderer_valid_ready_with_secrets(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": 1, "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION", "overall_status": "READY_FOR_MANUAL_DECISION", "target_source_post_id": "T1", "sheets_verifier": {"passed": 63, "total": 63}, "parent_candidate_count": 2, "parent_candidates": [{"candidate_number": 1, "sheet_row_number": 2, "account_id": "a1\\nb1", "declared_media_count": 1, "has_canonical_post_url": true, "canonical_identity_hash": "CANONICAL_HASH_SECRET", "required_field_presence_count": 5, "parent_precondition_hash": "PRECONDITION_HASH_SECRET", "canonical_matching_child_count": 1, "canonical_mismatching_child_ids": [], "material_difference_fields": [], "recommended_disposition": "MANUAL_DECISION_REQUIRED", "blocker_codes": [], "canonical_post_url": "https://unsafe.example/canonical", "original_media_url": "https://unsafe.example/media", "raw_row": "RAW_ROW_SECRET", "access_token": "TOKEN_SECRET", "client_secret": "CLIENT_SECRET_VALUE"}, {"candidate_number": 2, "sheet_row_number": 3, "account_id": "a2", "declared_media_count": 1, "has_canonical_post_url": false, "canonical_identity_hash": "", "required_field_presence_count": 5, "parent_precondition_hash": "", "canonical_matching_child_count": 0, "canonical_mismatching_child_ids": [], "material_difference_fields": [], "recommended_disposition": "MANUAL_DECISION_REQUIRED", "blocker_codes": []}], "child_summary": {"child_count": 1, "unique_child_id_count": 1, "child_id_duplicate_count": 0, "duplicate_media_indexes": [], "missing_child_id_count": 0, "malformed_media_index_count": 0, "negative_media_index_count": 0}, "recommended_keep_sheet_row_number": null, "manual_delete_candidate_sheet_row_numbers": [], "status_reasons": ["REASON1"], "apply_operations": []}')
        summary_path = json_path + ".md"
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "0"], capture_output=True)
        self.assertEqual(p.returncode, 0, msg=f"stderr: {p.stderr.decode()}")
        self.assertTrue(os.path.exists(summary_path))
        with open(summary_path, 'r') as f:
            out = f.read()
        self.assertIn("READY_FOR_MANUAL_DECISION", out)
        self.assertIn("Candidate #1", out)
        self.assertIn("Candidate #2", out)
        self.assertIn("Recommended Keep Row: null", out)
        self.assertIn("- REASON1", out)
        self.assertIn("Apply Operations Count: 0", out)
        self.assertNotIn("unsafe.example", out)
        self.assertNotIn("CANONICAL_HASH_SECRET", out)
        self.assertNotIn("PRECONDITION_HASH_SECRET", out)
        self.assertNotIn("RAW_ROW_SECRET", out)
        self.assertNotIn("TOKEN_SECRET", out)
        self.assertNotIn("CLIENT_SECRET_VALUE", out)
        self.assertIn("Has Canonical Identity Hash: true", out)
        self.assertIn("Account: a1 b1", out)
        os.remove(json_path)
        os.remove(summary_path)

    def test_22_summary_renderer_valid_blocked(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": 1, "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION", "overall_status": "BLOCKED", "target_source_post_id": "T1", "sheets_verifier": {}, "parent_candidates": [], "parent_candidate_count": 0, "child_summary": {"child_count": 0, "unique_child_id_count": 0, "child_id_duplicate_count": 0, "duplicate_media_indexes": [], "missing_child_id_count": 0, "malformed_media_index_count": 0, "negative_media_index_count": 0}, "recommended_keep_sheet_row_number": null, "manual_delete_candidate_sheet_row_numbers": [], "status_reasons": [], "apply_operations": []}')
        summary_path = json_path + ".md"
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "0"], capture_output=True)
        self.assertEqual(p.returncode, 0, msg=f"stderr: {p.stderr.decode()}")
        with open(summary_path, 'r') as f:
            out = f.read()
        self.assertIn("BLOCKED", out)
        self.assertIn("Candidates (0)", out)
        self.assertIn("- None", out)
        os.remove(json_path)
        os.remove(summary_path)

    def test_23_summary_renderer_valid_fail_empty_child(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": 1, "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION", "overall_status": "FAIL", "target_source_post_id": "T1", "sheets_verifier": {}, "parent_candidates": [], "parent_candidate_count": 0, "child_summary": {}, "recommended_keep_sheet_row_number": null, "manual_delete_candidate_sheet_row_numbers": [], "status_reasons": [], "apply_operations": []}')
        summary_path = json_path + ".md"
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "1"], capture_output=True)
        self.assertEqual(p.returncode, 1, msg=f"stderr: {p.stderr.decode()}")
        with open(summary_path, 'r') as f:
            out = f.read()
        self.assertIn("FAIL", out)
        os.remove(json_path)
        os.remove(summary_path)

    def test_24_summary_renderer_missing_top_level_key(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": 1, "overall_status": "READY_FOR_MANUAL_DECISION"}')
        summary_path = json_path + ".md"
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "0"], capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b"WP3-C2 summary renderer failed: ValueError", p.stderr)
        self.assertFalse(os.path.exists(summary_path))
        os.remove(json_path)

    def test_25_summary_renderer_invalid_mode(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": 1, "mode": "INVALID_MODE", "overall_status": "FAIL", "target_source_post_id": "T1", "sheets_verifier": {}, "parent_candidates": [], "parent_candidate_count": 0, "child_summary": {}, "recommended_keep_sheet_row_number": null, "manual_delete_candidate_sheet_row_numbers": [], "status_reasons": [], "apply_operations": []}')
        summary_path = json_path + ".md"
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "1"], capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b"WP3-C2 summary renderer failed: ValueError", p.stderr)
        self.assertFalse(os.path.exists(summary_path))
        os.remove(json_path)

    def test_26_summary_renderer_schema_bool(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": true, "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION", "overall_status": "FAIL", "target_source_post_id": "T1", "sheets_verifier": {}, "parent_candidates": [], "parent_candidate_count": 0, "child_summary": {}, "recommended_keep_sheet_row_number": null, "manual_delete_candidate_sheet_row_numbers": [], "status_reasons": [], "apply_operations": []}')
        summary_path = json_path + ".md"
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "1"], capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b"WP3-C2 summary renderer failed: ValueError", p.stderr)
        self.assertFalse(os.path.exists(summary_path))
        os.remove(json_path)

    def test_27_summary_renderer_candidate_count_bool(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": 1, "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION", "overall_status": "FAIL", "target_source_post_id": "T1", "sheets_verifier": {}, "parent_candidates": [], "parent_candidate_count": false, "child_summary": {}, "recommended_keep_sheet_row_number": null, "manual_delete_candidate_sheet_row_numbers": [], "status_reasons": [], "apply_operations": []}')
        summary_path = json_path + ".md"
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "1"], capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b"WP3-C2 summary renderer failed: ValueError", p.stderr)
        self.assertFalse(os.path.exists(summary_path))
        os.remove(json_path)

    def test_28_summary_renderer_candidate_missing_key(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": 1, "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION", "overall_status": "READY_FOR_MANUAL_DECISION", "target_source_post_id": "T1", "sheets_verifier": {"passed": 63, "total": 63}, "parent_candidate_count": 1, "parent_candidates": [{"candidate_number": 1}], "child_summary": {"child_count": 1, "unique_child_id_count": 1, "child_id_duplicate_count": 0, "duplicate_media_indexes": [], "missing_child_id_count": 0, "malformed_media_index_count": 0, "negative_media_index_count": 0}, "recommended_keep_sheet_row_number": null, "manual_delete_candidate_sheet_row_numbers": [], "status_reasons": ["REASON1"], "apply_operations": []}')
        summary_path = json_path + ".md"
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "0"], capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b"WP3-C2 summary renderer failed: ValueError", p.stderr)
        self.assertFalse(os.path.exists(summary_path))
        os.remove(json_path)

    def test_29_summary_renderer_child_summary_missing_key(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": 1, "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION", "overall_status": "READY_FOR_MANUAL_DECISION", "target_source_post_id": "T1", "sheets_verifier": {"passed": 63, "total": 63}, "parent_candidate_count": 0, "parent_candidates": [], "child_summary": {"child_count": 1}, "recommended_keep_sheet_row_number": null, "manual_delete_candidate_sheet_row_numbers": [], "status_reasons": ["REASON1"], "apply_operations": []}')
        summary_path = json_path + ".md"
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "0"], capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b"WP3-C2 summary renderer failed: ValueError", p.stderr)
        self.assertFalse(os.path.exists(summary_path))
        os.remove(json_path)

    def test_30_summary_renderer_fail_with_exit_code_0(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": 1, "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION", "overall_status": "FAIL", "target_source_post_id": "T1", "sheets_verifier": {}, "parent_candidates": [], "parent_candidate_count": 0, "child_summary": {}, "recommended_keep_sheet_row_number": null, "manual_delete_candidate_sheet_row_numbers": [], "status_reasons": [], "apply_operations": []}')
        summary_path = json_path + ".md"
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "0"], capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b"WP3-C2 summary renderer failed: ValueError", p.stderr)
        self.assertFalse(os.path.exists(summary_path))
        os.remove(json_path)

    def test_31_summary_renderer_ready_with_exit_code_1(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": 1, "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION", "overall_status": "READY_FOR_MANUAL_DECISION", "target_source_post_id": "T1", "sheets_verifier": {"passed": 63, "total": 63}, "parent_candidate_count": 0, "parent_candidates": [], "child_summary": {"child_count": 1, "unique_child_id_count": 1, "child_id_duplicate_count": 0, "duplicate_media_indexes": [], "missing_child_id_count": 0, "malformed_media_index_count": 0, "negative_media_index_count": 0}, "recommended_keep_sheet_row_number": null, "manual_delete_candidate_sheet_row_numbers": [], "status_reasons": ["REASON1"], "apply_operations": []}')
        summary_path = json_path + ".md"
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "1"], capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b"WP3-C2 summary renderer failed: ValueError", p.stderr)
        self.assertFalse(os.path.exists(summary_path))
        os.remove(json_path)

    def test_32_summary_renderer_exit_code_2(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": 1, "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION", "overall_status": "FAIL", "target_source_post_id": "T1", "sheets_verifier": {}, "parent_candidates": [], "parent_candidate_count": 0, "child_summary": {}, "recommended_keep_sheet_row_number": null, "manual_delete_candidate_sheet_row_numbers": [], "status_reasons": [], "apply_operations": []}')
        summary_path = json_path + ".md"
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "2"], capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b"WP3-C2 summary renderer failed: ValueError", p.stderr)
        self.assertFalse(os.path.exists(summary_path))
        os.remove(json_path)

    def test_33_summary_renderer_delete_rows_string(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": 1, "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION", "overall_status": "READY_FOR_MANUAL_DECISION", "target_source_post_id": "T1", "sheets_verifier": {"passed": 63, "total": 63}, "parent_candidate_count": 0, "parent_candidates": [], "child_summary": {"child_count": 1, "unique_child_id_count": 1, "child_id_duplicate_count": 0, "duplicate_media_indexes": [], "missing_child_id_count": 0, "malformed_media_index_count": 0, "negative_media_index_count": 0}, "recommended_keep_sheet_row_number": null, "manual_delete_candidate_sheet_row_numbers": ["a"], "status_reasons": ["REASON1"], "apply_operations": []}')
        summary_path = json_path + ".md"
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "0"], capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b"WP3-C2 summary renderer failed: ValueError", p.stderr)
        self.assertFalse(os.path.exists(summary_path))
        os.remove(json_path)

    def test_34_summary_renderer_duplicate_media_indexes_string(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": 1, "mode": "READ_ONLY_DUPLICATE_PARENT_INSPECTION", "overall_status": "READY_FOR_MANUAL_DECISION", "target_source_post_id": "T1", "sheets_verifier": {"passed": 63, "total": 63}, "parent_candidate_count": 0, "parent_candidates": [], "child_summary": {"child_count": 1, "unique_child_id_count": 1, "child_id_duplicate_count": 0, "duplicate_media_indexes": ["a"], "missing_child_id_count": 0, "malformed_media_index_count": 0, "negative_media_index_count": 0}, "recommended_keep_sheet_row_number": null, "manual_delete_candidate_sheet_row_numbers": [], "status_reasons": ["REASON1"], "apply_operations": []}')
        summary_path = json_path + ".md"
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "0"], capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b"WP3-C2 summary renderer failed: ValueError", p.stderr)
        self.assertFalse(os.path.exists(summary_path))
        os.remove(json_path)

    def test_35_summary_renderer_no_overwrite_on_error(self):
        import subprocess, tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as fj:
            json_path = fj.name
            fj.write(b'{"schema_version": 1, "overall_status": "FAIL"}')
        summary_path = json_path + ".md"
        with open(summary_path, 'w') as f:
            f.write("EXISTING CONTENT")
        p = subprocess.run(["python3", "scripts/render_wp3c2_inspection_summary.py", "--json-input", json_path, "--summary-output", summary_path, "--exit-code", "1"], capture_output=True)
        self.assertEqual(p.returncode, 1)
        self.assertIn(b"WP3-C2 summary renderer failed: ValueError", p.stderr)
        with open(summary_path, 'r') as f:
            out = f.read()
        self.assertEqual("EXISTING CONTENT", out)
        os.remove(json_path)
        os.remove(summary_path)

    def test_36_workflow_file_checks(self):
        with open(".github/workflows/wp3c2-duplicate-parent-inspection.yml", "r") as f:
            content = f.read()
        self.assertNotIn("jq -r '.parent_candidates[]", content)
        self.assertNotIn("jq .", content)
        self.assertIn("printf '%s\\n' \"$PLAN_JSON\"", content)
        self.assertIn("scripts/render_wp3c2_inspection_summary.py", content)
        self.assertIn("--exit-code \"$INSPECT_EXIT\"", content)
        self.assertEqual(content.count("scripts/render_wp3c2_inspection_summary.py"), 1)
        self.assertNotIn("cat /tmp/wp3c2_stdout.log", content)
        self.assertNotIn("cat /tmp/wp3c2_safe_plan.json", content)
