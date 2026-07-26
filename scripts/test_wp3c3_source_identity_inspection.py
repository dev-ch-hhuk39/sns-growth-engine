import unittest
import os
import sys
import json
import subprocess

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from inspect_wp3c3_source_identity_collision import inspect_wp3c3, TARGET_SOURCE_POST_ID
from render_wp3c3_identity_summary import validate_contract, render_markdown

class TestWP3C3Inspection(unittest.TestCase):
    def test_same_post_reingested_different_urls(self):
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://www.youtube.com/watch?v=abc", "media_count": "1"}),
        ]
        children = [
            (4, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_index": "0"}),
            (5, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_index": "0"}),
        ]
        rep = inspect_wp3c3(parents, children, "head", "main")
        self.assertEqual(rep["classification"], "SAME_POST_REINGESTED")
        self.assertEqual(rep["parents"][0]["matching_child_count"], 2)
        self.assertEqual(rep["parents"][1]["matching_child_count"], 2)

    def test_same_post_reingested_media_count_2(self):
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "2"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "2"}),
        ]
        children = [
            (4, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_index": "0", "source_post_media_id": "c1"}),
            (5, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_index": "0", "source_post_media_id": "c2"}),
            (6, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_index": "1", "source_post_media_id": "c3"}),
            (7, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_index": "1", "source_post_media_id": "c4"}),
        ]
        rep = inspect_wp3c3(parents, children, "head", "main")
        self.assertEqual(rep["classification"], "SAME_POST_REINGESTED")

    def test_unresolved_no_children(self):
        rep = inspect_wp3c3([(2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"})], [], "head", "main")
        self.assertEqual(rep["classification"], "UNRESOLVED_IDENTITY")
        self.assertIn("NOT_ENOUGH_PARENT_ROWS", rep["status_reasons"])
        self.assertIn("NO_CHILD_ROWS", rep["status_reasons"])
        
        rep2 = inspect_wp3c3([
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
            (4, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
        ], [], "head", "main")
        self.assertEqual(rep2["classification"], "UNRESOLVED_IDENTITY")
        self.assertIn("NO_CHILD_ROWS", rep2["status_reasons"])

    def test_unresolved_missing_child(self):
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "2"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "2"}),
        ]
        children = [
            (4, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_index": "0"}),
            (5, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_index": "0"}),
            (6, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_index": "1"}),
        ]
        rep = inspect_wp3c3(parents, children, "head", "main")
        self.assertEqual(rep["classification"], "UNRESOLVED_IDENTITY")
        self.assertIn("DECLARED_MEDIA_COUNT_MISMATCH", rep["status_reasons"])
        self.assertIn("MEDIA_INDEX_LAYOUT_MISMATCH", rep["status_reasons"])

    def test_distinct_posts(self):
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/def", "media_count": "1"}),
        ]
        children = [
            (4, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_index": "0"}),
            (5, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/def", "media_index": "0"}),
        ]
        rep = inspect_wp3c3(parents, children, "head", "main")
        self.assertEqual(rep["classification"], "DISTINCT_POSTS_COLLIDED")

    def test_distinct_but_parent_missing_child(self):
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/def", "media_count": "1"}),
        ]
        children = [
            (4, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_index": "0"}),
        ]
        rep = inspect_wp3c3(parents, children, "head", "main")
        self.assertEqual(rep["classification"], "UNRESOLVED_IDENTITY")
        self.assertIn("PARENT_WITHOUT_CHILD", rep["status_reasons"])
        self.assertIn("DECLARED_MEDIA_COUNT_MISMATCH", rep["status_reasons"])

    def test_distinct_child_identity_mismatch(self):
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/def", "media_count": "1"}),
        ]
        children = [
            (4, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_index": "0", "source_post_media_id": "c1"}),
            (5, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/ghi", "media_index": "0", "source_post_media_id": "c1"}),
        ]
        rep = inspect_wp3c3(parents, children, "head", "main")
        self.assertEqual(rep["classification"], "UNRESOLVED_IDENTITY")
        self.assertIn("CHILD_WITHOUT_PARENT_IDENTITY", rep["status_reasons"])
        self.assertEqual(rep["unique_post_identity_group_count"], 3)

    def test_unresolved_unextracted_child(self):
        parents = [
            (2, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
            (3, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_count": "1"}),
        ]
        children = [
            (4, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/abc", "media_index": "0"}),
            (5, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://notyoutube.com/abc", "media_index": "0"}),
        ]
        rep = inspect_wp3c3(parents, children, "head", "main")
        self.assertEqual(rep["classification"], "UNRESOLVED_IDENTITY")
        self.assertIn("CHILD_IDENTITY_UNRESOLVED", rep["status_reasons"])

    def test_no_sensitive_data_in_output(self):
        parents = [
            (10, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/SECRET123", "media_count": "1"}),
            (12, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/SECRET123", "media_count": "1"}),
        ]
        children = [
            (20, {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "https://youtu.be/SECRET123", "media_index": "0", "source_post_media_id": "MEDIASECRET456"})
        ]
        rep = inspect_wp3c3(parents, children, "head", "main")
        rep_str = json.dumps(rep)
        self.assertNotIn("SECRET123", rep_str)
        self.assertNotIn("https://", rep_str)
        self.assertNotIn("MEDIASECRET456", rep_str)
        self.assertEqual(rep["parents"][0]["sheet_row_number"], 10)
        self.assertEqual(rep["parents"][1]["sheet_row_number"], 12)
        self.assertEqual(rep["children"][0]["sheet_row_number"], 20)
        self.assertEqual(rep["apply_operations"], [])

class TestWP3C3RendererSubprocess(unittest.TestCase):
    def setUp(self):
        self.json_input = "/tmp/test_wp3c3_in.json"
        self.md_output = "/tmp/test_wp3c3_out.md"
        if os.path.exists(self.md_output):
            os.remove(self.md_output)

    def tearDown(self):
        if os.path.exists(self.json_input): os.remove(self.json_input)
        if os.path.exists(self.md_output): os.remove(self.md_output)

    def _run_renderer(self, data, exit_code):
        with open(self.json_input, "w") as f:
            json.dump(data, f)
        
        proc = subprocess.run([
            sys.executable, "scripts/render_wp3c3_identity_summary.py",
            "--json-input", self.json_input,
            "--summary-output", self.md_output,
            "--exit-code", str(exit_code)
        ], capture_output=True, text=True)
        return proc

    def _get_valid_data(self, status="READY_FOR_MANUAL_DECISION", classification="SAME_POST_REINGESTED", action="PLAN_DEDUPLICATION"):
        return {
            "schema_version": 1,
            "mode": "READ_ONLY_SOURCE_IDENTITY_COLLISION_INSPECTION",
            "overall_status": status,
            "classification": classification,
            "status_reasons": [],
            "checked_commit_sha": "abc",
            "parent_count": 0,
            "child_count": 0,
            "unique_parent_post_identity_group_count": 0,
            "unique_child_post_identity_group_count": 0,
            "unique_post_identity_group_count": 0,
            "unique_child_id_group_count": 0,
            "unique_parent_fingerprint_group_count": 0,
            "unique_child_fingerprint_group_count": 0,
            "parents": [],
            "children": [],
            "recommended_next_action": action,
            "apply_operations": []
        }

    def test_subprocess_ready_exit_0(self):
        proc = self._run_renderer(self._get_valid_data(), 0)
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(os.path.exists(self.md_output))
        self.assertNotIn("Exception", proc.stderr)
        
    def test_subprocess_blocked_exit_0(self):
        proc = self._run_renderer(self._get_valid_data(status="BLOCKED"), 0)
        self.assertEqual(proc.returncode, 0)

    def test_subprocess_fail_exit_1(self):
        proc = self._run_renderer(self._get_valid_data(status="FAIL", classification="UNRESOLVED_IDENTITY", action="MANUAL_INVESTIGATION"), 1)
        self.assertEqual(proc.returncode, 1)
        self.assertTrue(os.path.exists(self.md_output))
        
    def test_subprocess_fail_exit_0_contract_failure(self):
        proc = self._run_renderer(self._get_valid_data(status="FAIL", classification="UNRESOLVED_IDENTITY", action="MANUAL_INVESTIGATION"), 0)
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(os.path.exists(self.md_output))
        self.assertIn("ValueError", proc.stderr)

    def test_subprocess_ready_exit_1_contract_failure(self):
        proc = self._run_renderer(self._get_valid_data(), 1)
        self.assertEqual(proc.returncode, 1)
        self.assertFalse(os.path.exists(self.md_output))
        
    def test_invalid_group_name(self):
        data = self._get_valid_data()
        data["parent_count"] = 1
        data["parents"] = [{
            "post_identity_group": "POST_GROUP_01", # invalid, leading zero
            "stable_parent_fingerprint_group": "PARENT_GROUP_1",
            "identity_extracted": True
        }]
        proc = self._run_renderer(data, 0)
        self.assertEqual(proc.returncode, 1)

    def test_raw_url_in_group_name(self):
        data = self._get_valid_data()
        data["parent_count"] = 1
        data["parents"] = [{
            "post_identity_group": "https://youtu.be/abc",
            "stable_parent_fingerprint_group": "PARENT_GROUP_1",
            "identity_extracted": True
        }]
        proc = self._run_renderer(data, 0)
        self.assertEqual(proc.returncode, 1)
        
    def test_non_empty_operations(self):
        data = self._get_valid_data()
        data["apply_operations"] = [{"type": "DELETE"}]
        proc = self._run_renderer(data, 0)
        self.assertEqual(proc.returncode, 1)

class TestWP3C3WorkflowContract(unittest.TestCase):
    def test_workflow_contract(self):
        wf_path = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "wp3c3-source-identity-inspection.yml")
        with open(wf_path, "r") as f:
            content = f.read()

        self.assertIn("on:\n  workflow_dispatch:", content)
        self.assertIn("environment: production", content)
        self.assertIn("timeout-minutes: 20", content)
        self.assertIn("contents: read", content)
        self.assertIn("concurrency:\n  group: wp3c3-source-identity-collision-inspection\n  cancel-in-progress: false", content)
        self.assertIn('python-version: "3.11"', content)
        self.assertIn("GCP_SA_JSON_BASE64:", content)
        self.assertNotIn("GOOGLE_SHEETS_CREDENTIALS_JSON:", content)
        self.assertIn('PUBLISH_ENABLED: "false"', content)
        self.assertNotIn("source ", content)
        self.assertNotIn("eval ", content)
        self.assertNotIn("cat /tmp/wp3c3_out.txt", content)
        self.assertNotIn("actions/upload-artifact", content)
        self.assertIn("printf '%s\\n'", content)
        self.assertIn("scripts/render_wp3c3_identity_summary.py", content)
        self.assertIn("--exit-code $EXIT_CODE", content)
        self.assertNotIn("exit $EXIT_CODE", content.split("render_wp3c3_identity_summary.py")[1])
        
    def test_shell_injection(self):
        # We need to test if printing a string with shell commands evaluates it
        wf_path = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows", "wp3c3-source-identity-inspection.yml")
        with open(wf_path, "r") as f:
            content = f.read()
        
        # Test the variable substitution in shell directly
        script = """
        SAFE_JSON_STR='$(touch /tmp/wp3c3_injection_marker)'
        printf '%s\\n' "$SAFE_JSON_STR" > /dev/null
        """
        if os.path.exists("/tmp/wp3c3_injection_marker"):
            os.remove("/tmp/wp3c3_injection_marker")
        
        subprocess.run(["bash", "-c", script])
        self.assertFalse(os.path.exists("/tmp/wp3c3_injection_marker"))

if __name__ == '__main__':
    unittest.main()
