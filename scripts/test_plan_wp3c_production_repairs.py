import unittest
import os
import json
import tempfile
import subprocess
from datetime import datetime, timezone
import sys
from unittest.mock import patch, MagicMock

from plan_wp3c_production_repairs import (
    CHILD_HASH_FIELDS,
    SLOT_HASH_FIELDS,
    generate_hash,
    media_index_sort_key,
    classify_asset_relation,
    evaluate_external_blockers,
    plan_parent_repair,
    empty_parent_repair,
    plan_stale_slot_review,
    build_failure_report,
    build_repair_plan,
    parse_target_account_ids,
    prevent_writes,
    is_truthy,
    canonicalize_threads_identity,
    TARGET_SOURCE_POST_IDS,
    TARGET_SLOT_RUN_IDS,
)

class TestWP3CRepairPlannerCore(unittest.TestCase):
    
    def test_01_empty_parent_repair(self):
        rep1 = plan_parent_repair("p1", [], [])
        self.assertEqual(rep1["source_post_id"], "p1")
        self.assertIn("PARENT_NOT_FOUND", rep1["blocker_codes"])
        self.assertEqual(rep1["operations"], [])
        self.assertEqual(rep1["child_precondition_hashes"], {})
        self.assertFalse(rep1["apply_eligible"])
        
        rep2 = plan_parent_repair("p2", [{}, {}], [])
        self.assertEqual(rep2["source_post_id"], "p2")
        self.assertIn("MULTIPLE_PARENTS", rep2["blocker_codes"])
        self.assertEqual(rep2["operations"], [])
        self.assertEqual(rep2["child_precondition_hashes"], {})
        self.assertFalse(rep2["apply_eligible"])

    def test_02_boolean_normalization(self):
        self.assertTrue(is_truthy("1"))
        self.assertTrue(is_truthy("true"))
        self.assertTrue(is_truthy("TRUE"))
        self.assertTrue(is_truthy("yes"))
        self.assertTrue(is_truthy("y"))
        self.assertFalse(is_truthy("0"))
        self.assertFalse(is_truthy("false"))
        self.assertFalse(is_truthy("no"))
        self.assertFalse(is_truthy(""))
        self.assertFalse(is_truthy(None))

    def test_03_threads_destination_canonicalization(self):
        expected = "https://threads.net/@my_dest"
        self.assertEqual(canonicalize_threads_identity("my_dest"), expected)
        self.assertEqual(canonicalize_threads_identity("@my_dest"), expected)
        self.assertEqual(canonicalize_threads_identity("https://threads.net/@my_dest"), expected)
        self.assertEqual(canonicalize_threads_identity("https://www.threads.net/@my_dest/"), expected)
        self.assertEqual(canonicalize_threads_identity(""), "")

    def test_04_slot_hash_stability(self):
        base = {
            "slot_run_id": "s1",
            "account_id": "a1",
            "slot_id": "s_id",
            "status": "stat",
            "claim_status": "cstat",
            "lease_expires_at": "lease",
            "queue_id": "q",
            "result_id": "r",
            "post_url": "url",
            "updated_at": "updated"
        }
        
        h_base = generate_hash({k: base.get(k, "") for k in SLOT_HASH_FIELDS})
        h_same = generate_hash({k: base.get(k, "") for k in SLOT_HASH_FIELDS})
        self.assertEqual(h_base, h_same)
        
        for field in SLOT_HASH_FIELDS:
            mod = base.copy()
            mod[field] = "CHANGED"
            h_mod = generate_hash({k: mod.get(k, "") for k in SLOT_HASH_FIELDS})
            self.assertNotEqual(h_base, h_mod, f"Hash should change when {field} changes")

    def test_05_mock_safety_early_abort(self):
        import plan_wp3c_production_repairs
        
        with tempfile.NamedTemporaryFile(delete=False) as f:
            out_path = f.name
            
        old_argv = sys.argv
        sys.argv = ["plan_wp3c_production_repairs.py", "--output", out_path]
        
        # We want to mock everything that could be called if it gets past safety check
        mock_get_config = MagicMock()
        mock_sheets_client = MagicMock()
        mock_ws = MagicMock()
        mock_get_all_records = MagicMock()
        mock_verify_state = MagicMock()
        
        sys.modules['config_loader'] = MagicMock()
        sys.modules['config_loader'].get_config = mock_get_config
        sys.modules['sheets_client'] = MagicMock()
        sys.modules['sheets_client'].SheetsClient = mock_sheets_client
        sys.modules['recover_production_sheets_threads_first'] = MagicMock()
        sys.modules['recover_production_sheets_threads_first'].verify_state = mock_verify_state
        
        with patch("plan_wp3c_production_repairs.check_safety_flags", return_value=True):
            try:
                with self.assertRaises(SystemExit) as e:
                    plan_wp3c_production_repairs.main()
                self.assertEqual(e.exception.code, 1)
            finally:
                sys.argv = old_argv
                if os.path.exists(out_path): os.remove(out_path)
                
        self.assertEqual(mock_get_config.call_count, 0)
        self.assertEqual(mock_sheets_client.call_count, 0)
        self.assertEqual(mock_ws.call_count, 0)
        self.assertEqual(mock_get_all_records.call_count, 0)
        self.assertEqual(mock_verify_state.call_count, 0)

    def test_06_redaction_stdout(self):
        secret_vals = [
            "TEST_SOURCE_URL_SECRET",
            "TEST_CHILD_MEDIA_URL_SECRET",
            "TEST_STORAGE_URL_SECRET",
            "TEST_POST_TEXT_SECRET",
            "TEST_TRANSCRIPT_SECRET",
            "TEST_CONTENT_HASH_SECRET",
            "TEST_PERMISSION_EVIDENCE_SECRET",
            "TEST_APPROVED_BY_SECRET",
            "TEST_NOTES_SECRET",
            "TEST_ACCESS_TOKEN_SECRET"
        ]
        
        now = datetime.now(timezone.utc)
        datasets = {
            "source_posts": [{"source_post_id": TARGET_SOURCE_POST_IDS[0], "canonical_post_url": "http://a"}],
            "source_post_media": [{"source_post_id": TARGET_SOURCE_POST_IDS[0], "source_post_media_id": "m1", "original_media_url": "TEST_CHILD_MEDIA_URL_SECRET", "storage_url": "TEST_STORAGE_URL_SECRET", "content_hash": "TEST_CONTENT_HASH_SECRET"}],
            "content_slot_runs": [{"slot_run_id": TARGET_SLOT_RUN_IDS[0], "post_text": "TEST_POST_TEXT_SECRET", "transcript": "TEST_TRANSCRIPT_SECRET", "post_url": "TEST_SOURCE_URL_SECRET"}],
            "queue": [],
            "posted_results": [],
            "media_permissions": [{"source_id": "src_lm_yt_cand_001", "permission_status": "approved", "rights_status": "approved", "evidence_type": "url", "evidence_reference": "TEST_PERMISSION_EVIDENCE_SECRET", "approved_by": "TEST_APPROVED_BY_SECRET", "notes": "TEST_NOTES_SECRET"}],
            "source_accounts": [{"target_account_ids": "liver_manager", "platform": "threads", "active": "true", "source_url": "TEST_SOURCE_URL_SECRET", "review_status": "APPROVED", "access_token": "TEST_ACCESS_TOKEN_SECRET"}],
            "accounts": []
        }
        
        rep = build_repair_plan(datasets, verifier_result={"passed": 63, "total": 63, "failed": []}, implementation_head="", origin_main="", now=now)
        
        safe_line = (
            "WP3C_SAFE_REPAIR_PLAN_JSON="
            + json.dumps(rep, ensure_ascii=False)
        )
        
        for sv in secret_vals:
            self.assertNotIn(sv, safe_line, f"Secret {sv} leaked in safe_line stdout")

if __name__ == '__main__':
    unittest.main()
