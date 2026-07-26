import unittest
import os
import json
import tempfile
import subprocess
import sys
from unittest.mock import patch, MagicMock

from inspect_wp3c_duplicate_parent import (
    inspect_duplicate_parent,
    build_failure_report,
    TARGET_SOURCE_POST_ID,
    prevent_writes,
    read_rows_with_sheet_numbers,
    canonicalize_source_url,
    sha256_text
)

class TestWP3C2DuplicateInspector(unittest.TestCase):

    def test_row_numbers_blank_handling(self):
        class FakeWs:
            def get_all_values(self):
                return [
                    ["header1", "header2"],
                    ["a", "b"],
                    ["", "  "],
                    ["c", "d"],
                    []
                ]
        ws = FakeWs()
        rows = read_rows_with_sheet_numbers(ws)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], 2)
        self.assertEqual(rows[1][0], 4)
        
    def test_row_numbers_missing_header(self):
        class FakeWs:
            def get_all_values(self):
                return [["", ""]]
        ws = FakeWs()
        with self.assertRaises(ValueError):
            read_rows_with_sheet_numbers(ws)

    def test_hashes(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        rep = inspect_duplicate_parent([(2, p1)], [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        c1 = rep["parent_candidates"][0]
        self.assertEqual(len(c1["parent_precondition_hash"]), 64)
        self.assertEqual(len(c1["canonical_identity_hash"]), 64)
        
        # Test change in field alters parent hash
        p2 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 2, "target_account_id": "a"}
        rep2 = inspect_duplicate_parent([(2, p2)], [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertNotEqual(c1["parent_precondition_hash"], rep2["parent_candidates"][0]["parent_precondition_hash"])
        
        # Identity Hash matches sha256 of canonical url
        self.assertEqual(c1["canonical_identity_hash"], sha256_text(canonicalize_source_url("http://a")))
        
    def test_redaction(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "SECRET_URL", "updated_at": "SECRET_DATE"}
        rep = inspect_duplicate_parent([(2, p1), (3, p1)], [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        dump = json.dumps(rep)
        self.assertNotIn("SECRET_URL", dump)
        self.assertNotIn("SECRET_DATE", dump)

    def test_status_2_parents(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        parents = [(2, p1), (3, p1)]
        rep = inspect_duplicate_parent(parents, [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["overall_status"], "READY_FOR_MANUAL_DECISION")

    def test_status_3_parents(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        parents = [(2, p1), (3, p1), (4, p1)]
        rep = inspect_duplicate_parent(parents, [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["overall_status"], "READY_FOR_MANUAL_DECISION")
        self.assertIn("DUPLICATE_PARENT_AMBIGUOUS", rep["parent_candidates"][0]["blocker_codes"])
        self.assertEqual(rep["parent_candidates"][0]["recommended_disposition"], "MANUAL_DECISION_REQUIRED")

    def test_status_1_parent(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        parents = [(2, p1)]
        rep = inspect_duplicate_parent(parents, [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["overall_status"], "BLOCKED")
        self.assertIn("NOT_ENOUGH_PARENTS", rep["status_reasons"])
        
    def test_status_0_parents(self):
        rep = inspect_duplicate_parent([], [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["overall_status"], "BLOCKED")

    def test_status_invalid_row(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        parents = [(1, p1), (3, p1)] # 1 is invalid
        rep = inspect_duplicate_parent(parents, [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["overall_status"], "BLOCKED")
        self.assertIn("INVALID_SHEET_ROW_NUMBER", rep["parent_candidates"][0]["blocker_codes"])

    def test_status_duplicate_row(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        parents = [(2, p1), (2, p1)]
        rep = inspect_duplicate_parent(parents, [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["overall_status"], "BLOCKED")
        self.assertIn("DUPLICATE_SHEET_ROW_NUMBER", rep["parent_candidates"][1]["blocker_codes"])

    def test_sheets_failed(self):
        rep = inspect_duplicate_parent([(2, {}), (3, {})], [], verifier_result={"passed": 62, "total": 63, "failed": [{"r":1}]}, implementation_head="", origin_main="")
        self.assertEqual(rep["overall_status"], "FAIL")
        self.assertIn("SHEETS_VERIFIER_FAILED", rep["status_reasons"])

    def test_sheets_count_inconsistent(self):
        rep = inspect_duplicate_parent([(2, {}), (3, {})], [], verifier_result={"passed": 60, "total": 50, "failed": [{"r":1}]}, implementation_head="", origin_main="")
        self.assertEqual(rep["overall_status"], "FAIL")
        self.assertIn("SHEETS_VERIFIER_COUNT_INCONSISTENT", rep["status_reasons"])

    def test_exact_duplicate(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        parents = [(2, p1), (3, p1)]
        rep = inspect_duplicate_parent(parents, [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["parent_candidates"][0]["recommended_disposition"], "KEEP_CANDIDATE")
        self.assertEqual(rep["parent_candidates"][1]["recommended_disposition"], "EXACT_DUPLICATE_MANUAL_DELETE_CANDIDATE")

    def test_prefer_canonical_match(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        p2 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://b", "media_count": 1, "target_account_id": "a"}
        c1 = {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "m1", "canonical_post_url": "http://a", "media_index": 0}
        parents = [(5, p1), (6, p2)]
        rep = inspect_duplicate_parent(parents, [(10, c1)], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["parent_candidates"][0]["recommended_disposition"], "KEEP_CANDIDATE")
        self.assertEqual(rep["parent_candidates"][1]["recommended_disposition"], "MANUAL_DELETE_CANDIDATE")

    def test_prefer_completeness(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        p2 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "target_account_id": "a"}
        parents = [(2, p1), (3, p2)]
        rep = inspect_duplicate_parent(parents, [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["parent_candidates"][0]["recommended_disposition"], "KEEP_CANDIDATE")
        self.assertEqual(rep["parent_candidates"][1]["recommended_disposition"], "MANUAL_DELETE_CANDIDATE")

    def test_ambiguous(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        p2 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://b", "media_count": 1, "target_account_id": "a"}
        parents = [(2, p1), (3, p2)]
        rep = inspect_duplicate_parent(parents, [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["parent_candidates"][0]["recommended_disposition"], "MANUAL_DECISION_REQUIRED")
        self.assertEqual(rep["parent_candidates"][1]["recommended_disposition"], "MANUAL_DECISION_REQUIRED")

    def test_zero_child_ambiguous(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        p2 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://b", "media_count": 1, "target_account_id": "a"}
        parents = [(2, p1), (3, p2)]
        rep = inspect_duplicate_parent(parents, [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["parent_candidates"][0]["recommended_disposition"], "MANUAL_DECISION_REQUIRED")
        self.assertEqual(rep["parent_candidates"][1]["recommended_disposition"], "MANUAL_DECISION_REQUIRED")

    def test_missing_child_canonical_not_match_all(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        p2 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://b", "media_count": 1, "target_account_id": "a"}
        c1 = {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "m1", "canonical_post_url": "", "media_index": 0}
        parents = [(2, p1), (3, p2)]
        rep = inspect_duplicate_parent(parents, [(10, c1)], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["parent_candidates"][0]["recommended_disposition"], "MANUAL_DECISION_REQUIRED")
        self.assertEqual(rep["parent_candidates"][1]["recommended_disposition"], "MANUAL_DECISION_REQUIRED")

    def test_child_summary(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        c1 = {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "m1", "media_index": 0}
        c2 = {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "m1", "media_index": 0} 
        c3 = {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "m2", "media_index": -1} 
        c4 = {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": "m3", "media_index": "foo"} 
        c5 = {"source_post_id": TARGET_SOURCE_POST_ID, "source_post_media_id": ""}
        
        rep = inspect_duplicate_parent([(2, p1), (3, p1)], [(4, c1), (5, c2), (6, c3), (7, c4), (8, c5)], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        cs = rep["child_summary"]
        self.assertEqual(cs["child_count"], 5)
        self.assertEqual(cs["unique_child_id_count"], 3)
        self.assertEqual(cs["child_id_duplicate_count"], 1)
        self.assertEqual(cs["duplicate_media_indexes"], [0])
        self.assertEqual(cs["missing_child_id_count"], 1)
        self.assertEqual(cs["malformed_media_index_count"], 2)
        self.assertEqual(cs["negative_media_index_count"], 1)
        
    def test_apply_operations_empty(self):
        p1 = {"source_post_id": TARGET_SOURCE_POST_ID, "canonical_post_url": "http://a", "media_count": 1, "target_account_id": "a"}
        rep = inspect_duplicate_parent([(2, p1), (3, p1)], [], verifier_result={"passed": 63, "total": 63}, implementation_head="", origin_main="")
        self.assertEqual(rep["apply_operations"], [])

    def test_0_call_on_safety_abort(self):
        import inspect_wp3c_duplicate_parent
        with patch("inspect_wp3c_duplicate_parent.check_safety_flags", return_value=True):
            with patch("config_loader.get_config") as mock_cfg:
                with patch("sheets_client.SheetsClient") as mock_client:
                    with tempfile.NamedTemporaryFile(delete=False) as f:
                        out_path = f.name
                    old_argv = sys.argv
                    sys.argv = ["inspect_wp3c_duplicate_parent.py", "--output", out_path]
                    try:
                        with self.assertRaises(SystemExit):
                            inspect_wp3c_duplicate_parent.main()
                        mock_cfg.assert_not_called()
                        mock_client.assert_not_called()
                    finally:
                        sys.argv = old_argv
                        if os.path.exists(out_path): os.remove(out_path)

    def test_write_bomb_integration(self):
        class FakeWs:
            def __init__(self):
                self.calls = {m: 0 for m in ["append_row", "append_rows", "update", "update_cell", "batch_update", "resize", "clear", "delete_rows"]}
            def get_all_values(self):
                return [["header1"], ["val1"]]
            def append_row(self): self.calls["append_row"] += 1
            def append_rows(self): self.calls["append_rows"] += 1
            def update(self): self.calls["update"] += 1
            def update_cell(self): self.calls["update_cell"] += 1
            def batch_update(self): self.calls["batch_update"] += 1
            def resize(self): self.calls["resize"] += 1
            def clear(self): self.calls["clear"] += 1
            def delete_rows(self): self.calls["delete_rows"] += 1
            
        class FakeClient:
            def __init__(self):
                self.calls = {m: 0 for m in ["_ensure_tab", "setup_all", "seed", "save"]}
                self.ws = FakeWs()
            def _ws(self, name): return self.ws
            def _ensure_tab(self): self.calls["_ensure_tab"] += 1
            def setup_all(self): self.calls["setup_all"] += 1
            def seed(self): self.calls["seed"] += 1
            def save(self): self.calls["save"] += 1

        client = FakeClient()
        ws = client._ws("test")
        prevent_writes(client)
        prevent_writes(ws)
        
        # Read should succeed and have accurate numbers
        rows = read_rows_with_sheet_numbers(ws)
        self.assertEqual(rows[0][0], 2)
        
        # No writes should have been made
        for count in client.calls.values(): self.assertEqual(count, 0)
        for count in ws.calls.values(): self.assertEqual(count, 0)
        
        # Writes bomb
        with self.assertRaises(Exception) as e:
            client.save()
        self.assertIn("WRITE BOMB TRIGGERED", str(e.exception))
        
        with self.assertRaises(Exception) as e:
            ws.update()
        self.assertIn("WRITE BOMB TRIGGERED", str(e.exception))

    def test_cli_strict_parsing(self):
        import inspect_wp3c_duplicate_parent
        old_argv = sys.argv
        for arg in ["--apply", "--delete", "--update", "--repair", "--confirm", "--source-post-id", "--foo"]:
            sys.argv = ["inspect_wp3c_duplicate_parent.py", "--output", "/tmp/x", arg]
            try:
                with self.assertRaises(SystemExit) as e:
                    inspect_wp3c_duplicate_parent.main()
                self.assertEqual(e.exception.code, 2)
            except Exception as e:
                self.fail(f"Arg {arg} failed with unexpected exception {e}")
        sys.argv = old_argv

if __name__ == '__main__':
    unittest.main()
