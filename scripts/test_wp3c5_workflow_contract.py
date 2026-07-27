#!/usr/bin/env python3
import os
import sys
import yaml
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

WORKFLOW_PATH = os.path.join(ROOT, ".github", "workflows", "wp3c5-safe-youtube-path-provenance.yml")

class TestWP3C5WorkflowContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            cls.workflow = yaml.safe_load(f)

    def test_workflow_dispatch_only(self):
        self.assertIn("on", self.workflow)
        self.assertIn("workflow_dispatch", self.workflow["on"])
        self.assertEqual(len(self.workflow["on"]), 1, "Should only trigger on workflow_dispatch")

    def test_environment_and_permissions(self):
        job = self.workflow["jobs"]["inspect-and-render"]
        self.assertEqual(job["environment"], "production")
        self.assertEqual(job["permissions"]["contents"], "read")
        self.assertEqual(len(job["permissions"]), 1)
        
        self.assertIn("timeout-minutes", job)
        self.assertTrue(isinstance(job["timeout-minutes"], int))
        
        # Check persist-credentials
        checkout_step = next(step for step in job["steps"] if "actions/checkout" in step.get("uses", ""))
        self.assertEqual(checkout_step["with"]["persist-credentials"], False)

    def test_safety_flags(self):
        job = self.workflow["jobs"]["inspect-and-render"]
        env = job["env"]
        
        actual_flags = [
            "PUBLISH_ENABLED",
            "ALLOW_REAL_THREADS_POST",
            "ALLOW_REAL_X_POST",
            "ALLOW_VIDEO_DOWNLOAD",
            "ALLOW_VIDEO_CUT",
            "ALLOW_CLOUDINARY_UPLOAD",
            "ALLOW_MEDIA_POSTS",
            "ALLOW_REAL_THREADS_VIDEO_POST",
            "ALLOW_TRANSCRIPTION_API"
        ]
        absent_flags = [
            "ALLOW_SNS_POSTING",
            "ALLOW_SPREADSHEET_MUTATION",
            "ALLOW_CLOUD_STORAGE_MUTATION",
            "ALLOW_EXTERNAL_API_FETCH",
            "ALLOW_UNSAFE_DEBUG_LOGGING",
            "DRY_RUN_OVERRIDE",
            "BYPASS_PERMISSION_GATE",
            "ENABLE_EXPERIMENTAL_REPAIR",
            "ALLOW_CANARY_AUTO_MERGE"
        ]
        
        for flag in actual_flags:
            self.assertIn(flag, env)
            self.assertEqual(env[flag], "false", f"{flag} must be false")
            
        for flag in absent_flags:
            self.assertNotIn(flag, env)

    def test_fallback_json(self):
        job = self.workflow["jobs"]["inspect-and-render"]
        fallback_step = next(step for step in job["steps"] if step.get("id") == "fallback")
        run_script = fallback_step["run"]
        
        # Check 0 case
        self.assertIn('if [ "$JSON_COUNT" -eq 0 ]; then', run_script)
        # Check multiple case
        self.assertIn('elif [ "$JSON_COUNT" -gt 1 ]; then', run_script)
        
        # Both must have INSPECTOR_STARTUP_FAILED
        count_startup_failed = run_script.count('"status_reasons":["INSPECTOR_STARTUP_FAILED"]')
        self.assertEqual(count_startup_failed, 2)
        
        # Ensure static_trace is complete in fallback
        self.assertIn('"static_trace": {', run_script)
        self.assertIn('"current_parent_id_uses_source_and_external_id": false', run_script)
        self.assertIn('"current_child_id_uses_parent_and_media_index": false', run_script)
        self.assertIn('"current_discovery_rejects_nonpost_youtube_urls": false', run_script)
        self.assertIn('"current_discovery_handles_channel_landing_pages": false', run_script)
        self.assertIn('"candidate_historical_writer_count": 0', run_script)
        self.assertIn('"candidate_historical_writer_labels": []', run_script)
        
    def test_raw_stderr_not_cat(self):
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("cat raw.stderr", content)
        self.assertNotIn("cat raw.stdout", content)
        self.assertNotIn("traceback", content.lower())
        self.assertNotIn("cat /tmp/wp3c5_err.txt", content)
        self.assertNotIn("echo /tmp/wp3c5_err.txt", content)
        
    def test_no_artifact_upload(self):
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("actions/upload-artifact", content)

    def test_fail_propagation(self):
        job = self.workflow["jobs"]["inspect-and-render"]
        render_step = next(step for step in job["steps"] if step.get("id") == "render")
        
        # The renderer receives EXIT_CODE from inspector
        self.assertIn('python3 scripts/render_wp3c5_youtube_path_provenance_summary.py', render_step["run"])
        self.assertIn('--exit-code $EXIT_CODE', render_step["run"])

        # No `set +e` inside renderer step so it fails the workflow if renderer exits with 1
        self.assertNotIn('set +e', render_step["run"])

    def test_only_validated_renderer_output_is_mirrored_to_logs(self):
        job = self.workflow["jobs"]["inspect-and-render"]
        render_step = next(step for step in job["steps"] if step.get("id") == "render")
        run_script = render_step["run"]
        self.assertIn('| tee -a "$GITHUB_STEP_SUMMARY"', run_script)
        self.assertNotIn("/tmp/wp3c5_out.txt", run_script)
        self.assertNotIn("/tmp/wp3c5_err.txt", run_script)

if __name__ == "__main__":
    unittest.main()
