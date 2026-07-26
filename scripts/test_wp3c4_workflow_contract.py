import unittest
import yaml

class TestWP3C4WorkflowContract(unittest.TestCase):
    def setUp(self):
        with open(".github/workflows/wp3c4-safe-url-shape-diagnostics.yml", "r") as f:
            self.wf = yaml.safe_load(f)

    def test_workflow_dispatch_only(self):
        self.assertEqual(list(self.wf[True].keys()), ["workflow_dispatch"])

    def test_environment_production(self):
        self.assertEqual(self.wf["jobs"]["inspect"]["environment"], "production")

    def test_permissions_contents_read(self):
        self.assertEqual(self.wf["permissions"]["contents"], "read")

    def test_timeout_20(self):
        self.assertEqual(self.wf["jobs"]["inspect"]["timeout-minutes"], 20)

    def test_sheets_auth_vars(self):
        env = self.wf["jobs"]["inspect"]["steps"][3]["env"]
        self.assertIn("GCP_SA_JSON_BASE64", env)
        self.assertIn("SA_JSON_BASE64", env)
        self.assertIn("SPREADSHEET_ID", env)
        self.assertIn("SNS_MASTER_SHEET_ID", env)

    def test_9_safety_flags_false(self):
        env = self.wf["jobs"]["inspect"]["steps"][3]["env"]
        flags = [
            "PUBLISH_ENABLED", "ALLOW_REAL_THREADS_POST", "ALLOW_REAL_X_POST",
            "ALLOW_VIDEO_DOWNLOAD", "ALLOW_VIDEO_CUT", "ALLOW_CLOUDINARY_UPLOAD",
            "ALLOW_MEDIA_POSTS", "ALLOW_REAL_THREADS_VIDEO_POST", "ALLOW_TRANSCRIPTION_API"
        ]
        for f in flags:
            self.assertEqual(env[f], "false")

    def test_safe_prefix_count_check(self):
        run = self.wf["jobs"]["inspect"]["steps"][3]["run"]
        self.assertIn("SAFE_PREFIX_COUNT=$(grep -c", run)
        self.assertIn('if [ "$SAFE_PREFIX_COUNT" != "1" ]; then', run)

    def test_parameter_expansion(self):
        run = self.wf["jobs"]["inspect"]["steps"][3]["run"]
        self.assertIn("SAFE_JSON_STR=${SAFE_JSON_LINE#WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=}", run)

    def test_printf_save(self):
        run = self.wf["jobs"]["inspect"]["steps"][3]["run"]
        self.assertIn("printf '%s\\n' \"$SAFE_JSON_STR\" > /tmp/wp3c4_safe_clean.json", run)

    def test_renderer_exit_code_pass(self):
        run = self.wf["jobs"]["inspect"]["steps"][3]["run"]
        self.assertIn("--exit-code \"$EXIT_CODE\"", run)

    def test_github_step_summary_quoted(self):
        run = self.wf["jobs"]["inspect"]["steps"][3]["run"]
        self.assertIn("--summary-output \"$GITHUB_STEP_SUMMARY\"", run)

    def test_no_source(self):
        run = self.wf["jobs"]["inspect"]["steps"][3]["run"]
        self.assertNotIn("source ", run)

    def test_no_eval(self):
        run = self.wf["jobs"]["inspect"]["steps"][3]["run"]
        self.assertNotIn("eval ", run)

    def test_no_cat(self):
        run = self.wf["jobs"]["inspect"]["steps"][3]["run"]
        self.assertNotIn("cat ", run)

    def test_no_artifact(self):
        for step in self.wf["jobs"]["inspect"]["steps"]:
            if "uses" in step:
                self.assertNotIn("upload-artifact", step["uses"])


    def test_shell_injection_execution(self):
        import subprocess, tempfile, os
        marker = "/tmp/wp3c4_injection_marker"
        if os.path.exists(marker):
            os.unlink(marker)
            
        payload = 'WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON={"test": "$(touch /tmp/wp3c4_injection_marker)"}'
        with tempfile.NamedTemporaryFile("w+", delete=False) as tf:
            tf.write(payload + "\n")
            tf_name = tf.name
            
        script = f'''
SAFE_PREFIX_COUNT=$(grep -c "^WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=" {tf_name} || true)
if [ "$SAFE_PREFIX_COUNT" != "1" ]; then
    echo "WP3-C4 diagnostics failed or produced multiple JSON outputs."
    exit 1
fi
SAFE_JSON_LINE=$(grep "^WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=" {tf_name})
SAFE_JSON_STR=${{SAFE_JSON_LINE#WP3C4_SAFE_URL_SHAPE_DIAGNOSTICS_JSON=}}
printf '%s\n' "$SAFE_JSON_STR" > /tmp/wp3c4_safe_clean.json
'''
        subprocess.run(["sh", "-c", script], capture_output=True)
        self.assertFalse(os.path.exists(marker))
        if os.path.exists(marker):
            os.unlink(marker)
        os.unlink(tf_name)



    def test_direct_invocation_without_pythonpath(self):
        import os, subprocess, sys
        from pathlib import Path
        ROOT = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        result = subprocess.run(
            [
                sys.executable,
                "scripts/inspect_wp3c4_unresolved_url_shapes.py",
                "--help",
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"Failed: {result.stderr}")
        self.assertNotIn("ModuleNotFoundError", result.stderr)
        self.assertNotIn("No module named 'src'", result.stderr)

    def test_workflow_fallback_0_prefix(self):
        run = self.wf["jobs"]["inspect"]["steps"][3]["run"]
        self.assertIn("INSPECTOR_STARTUP_FAILED", run)
        self.assertIn('EXIT_CODE=1', run)
        self.assertIn('\\"checked_commit_sha\\":\\"$GITHUB_SHA\\"', run)
        self.assertIn('\\"parents\\":[]', run)
        self.assertIn('\\"children\\":[]', run)
        self.assertIn('\\"apply_operations\\":[]', run)

    def test_workflow_fallback_multiple_prefix(self):
        # same logic applies to != 1
        run = self.wf["jobs"]["inspect"]["steps"][3]["run"]
        self.assertIn('if [ "$SAFE_PREFIX_COUNT" != "1" ]; then', run)

    def test_no_raw_stderr(self):
        run = self.wf["jobs"]["inspect"]["steps"][3]["run"]
        self.assertIn('2> /tmp/wp3c4_err.txt', run)
        self.assertNotIn('cat /tmp/wp3c4_err.txt', run)
        self.assertNotIn('cat ', run)

if __name__ == "__main__":
    unittest.main()
