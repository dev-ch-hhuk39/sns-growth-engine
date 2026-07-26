import unittest
import os
import json
import tempfile
import subprocess
import sys

from inspect_wp3c_duplicate_parent import (
    inspect_duplicate_parent,
    build_failure_report,
    TARGET_SOURCE_POST_ID,
    prevent_writes
)

class TestWP3C2DuplicateInspector(unittest.TestCase):

    def test_01_exact_duplicate(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        p2 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        
        parents = [(2, p1), (3, p2)]
        rep = inspect_duplicate_parent(parents, [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        
        self.assertEqual(rep["overall_status"], "READY_FOR_MANUAL_DECISION")
        self.assertEqual(rep["parent_candidate_count"], 2)
        
        c1, c2 = rep["parent_candidates"]
        self.assertEqual(c1["recommended_disposition"], "KEEP_CANDIDATE")
        self.assertEqual(c2["recommended_disposition"], "EXACT_DUPLICATE_MANUAL_DELETE_CANDIDATE")
        self.assertEqual(rep["recommended_keep_sheet_row_number"], 2)
        self.assertEqual(rep["manual_delete_candidate_sheet_row_numbers"], [3])
        self.assertEqual(rep["apply_operations"], [])
        
    def test_02_prefer_canonical_match(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        p2 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://b", "media_count": 1, "target_account_id": "a"}
        
        c1 = {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "m1", "canonical_post_url": "http://a", "media_index": 0}
        
        parents = [(5, p1), (6, p2)]
        children = [(10, c1)]
        rep = inspect_duplicate_parent(parents, children, verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        
        self.assertEqual(rep["recommended_keep_sheet_row_number"], 5)
        self.assertEqual(rep["manual_delete_candidate_sheet_row_numbers"], [6])
        self.assertEqual(rep["parent_candidates"][0]["recommended_disposition"], "KEEP_CANDIDATE")
        self.assertEqual(rep["parent_candidates"][1]["recommended_disposition"], "MANUAL_DELETE_CANDIDATE")

    def test_03_prefer_completeness(self):
        # same canonical
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        # missing media_count
        p2 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "target_account_id": "a"}
        
        parents = [(2, p1), (3, p2)]
        rep = inspect_duplicate_parent(parents, [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        
        self.assertEqual(rep["recommended_keep_sheet_row_number"], 2)
        self.assertEqual(rep["manual_delete_candidate_sheet_row_numbers"], [3])

    def test_04_ambiguous(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        # Same completeness, different URL, no children
        p2 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://b", "media_count": 1, "target_account_id": "a"}
        
        parents = [(2, p1), (3, p2)]
        rep = inspect_duplicate_parent(parents, [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        
        self.assertEqual(rep["recommended_keep_sheet_row_number"], None)
        self.assertEqual(rep["parent_candidates"][0]["recommended_disposition"], "MANUAL_DECISION_REQUIRED")
        self.assertEqual(rep["parent_candidates"][1]["recommended_disposition"], "MANUAL_DECISION_REQUIRED")
        self.assertIn("DUPLICATE_PARENT_AMBIGUOUS", rep["parent_candidates"][0]["blocker_codes"])
        
    def test_05_single_parent(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        parents = [(2, p1)]
        rep = inspect_duplicate_parent(parents, [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["overall_status"], "BLOCKED")
        
    def test_06_zero_parent(self):
        rep = inspect_duplicate_parent([], [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["overall_status"], "BLOCKED")
        
    def test_07_child_summary(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        p2 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        
        c1 = {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "m1", "media_index": 0}
        c2 = {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "m1", "media_index": 0} # dup ID, dup index
        c3 = {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "m2", "media_index": -1} # neg index
        c4 = {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "m3", "media_index": "foo"} # malformed index
        c5 = {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "", "media_index": 0} # missing ID
        
        rep = inspect_duplicate_parent([(2, p1), (3, p2)], [(4, c1), (5, c2), (6, c3), (7, c4), (8, c5)], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        
        cs = rep["child_summary"]
        self.assertEqual(cs["child_count"], 5)
        self.assertEqual(cs["child_id_duplicate_count"], 1)
        self.assertEqual(cs["unique_child_id_count"], 3) # m1, m2, m3
        self.assertEqual(cs["duplicate_media_indexes"], [0])
        self.assertEqual(cs["negative_media_index_count"], 1)
        self.assertEqual(cs["malformed_media_index_count"], 1)
        self.assertEqual(cs["missing_child_id_count"], 1)
        
    def test_08_sheets_count_inconsistent(self):
        rep = inspect_duplicate_parent([(2, {})], [], verifier_result={"passed": 60, "total": 50, "failed": [{"r":1}]}, implementation_head="", origin_main="")
        self.assertEqual(rep["overall_status"], "FAIL")
        self.assertIn("SHEETS_VERIFIER_COUNT_INCONSISTENT", rep["status_reasons"])
        
    def test_09_safety_flags_abort(self):
        import inspect_wp3c_duplicate_parent
        from unittest.mock import patch
        
        with tempfile.NamedTemporaryFile(delete=False) as f:
            out_path = f.name
            
        old_argv = sys.argv
        sys.argv = ["inspect_wp3c_duplicate_parent.py", "--output", out_path]
        
        with patch("inspect_wp3c_duplicate_parent.check_safety_flags", return_value=True):
            try:
                with self.assertRaises(SystemExit) as e:
                    inspect_wp3c_duplicate_parent.main()
                self.assertEqual(e.exception.code, 1)
            finally:
                sys.argv = old_argv
                if os.path.exists(out_path): os.remove(out_path)

    def test_10_unknown_args(self):
        import inspect_wp3c_duplicate_parent
        old_argv = sys.argv
        sys.argv = ["inspect_wp3c_duplicate_parent.py", "--output", "/tmp/x", "--apply"]
        
        try:
            with self.assertRaises(SystemExit) as e:
                inspect_wp3c_duplicate_parent.main()
            self.assertEqual(e.exception.code, 1)
        finally:
            sys.argv = old_argv
            
    def test_11_write_bomb(self):
        class FakeClient:
            def __init__(self):
                self.calls = {m: 0 for m in [
                    "_ensure_tab", "append_row", "append_rows", "update", "update_cell",
                    "batch_update", "resize", "clear", "delete_rows", "setup_all", "seed", "save"
                ]}
            def get_all_records(self): return []
            def _ws(self, name): return self
            
            def _ensure_tab(self): self.calls["_ensure_tab"] += 1
            def append_row(self): self.calls["append_row"] += 1
            def append_rows(self): self.calls["append_rows"] += 1
            def update(self): self.calls["update"] += 1
            def update_cell(self): self.calls["update_cell"] += 1
            def batch_update(self): self.calls["batch_update"] += 1
            def resize(self): self.calls["resize"] += 1
            def clear(self): self.calls["clear"] += 1
            def delete_rows(self): self.calls["delete_rows"] += 1
            def setup_all(self): self.calls["setup_all"] += 1
            def seed(self): self.calls["seed"] += 1
            def save(self): self.calls["save"] += 1

        client = FakeClient()
        prevent_writes(client)

        for m, count in client.calls.items():
            self.assertEqual(count, 0)
        with self.assertRaises(Exception):
            client.update()
            
    def test_12_redaction(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "TEST_URL_SECRET", "media_count": 1, "target_account_id": "a", "updated_at": "TEST_UPDATED_AT_SECRET"}
        p2 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "TEST_URL_SECRET", "media_count": 1, "target_account_id": "a", "updated_at": "TEST_UPDATED_AT_SECRET"}
        parents = [(2, p1), (3, p2)]
        rep = inspect_duplicate_parent(parents, [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        rep_str = json.dumps(rep)
        
        self.assertNotIn("TEST_URL_SECRET", rep_str)
        self.assertNotIn("TEST_UPDATED_AT_SECRET", rep_str)
        
        # We should still have has_canonical_post_url true
        self.assertTrue(rep["parent_candidates"][0]["has_canonical_post_url"])
        self.assertTrue(rep["parent_candidates"][0]["has_updated_at"])
        
if __name__ == '__main__':
    unittest.main()
