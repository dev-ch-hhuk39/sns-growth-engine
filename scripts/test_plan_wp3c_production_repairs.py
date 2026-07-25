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

class TestWP3CRepairPlannerCore(unittest.TestCase):
    
    def test_01_child_hash_stability(self):
        base = {
            "source_post_media_id": "M1",
            "source_post_id": "P1",
            "media_index": 0,
            "canonical_post_url": "http://a",
            "content_hash": "a1",
            "original_media_url": "http://b",
            "cloudinary_public_id": "c1",
            "media_asset_id": "ma1",
            "updated_at": "2026-07-26T00:00:00Z"
        }
        
        h_base = generate_hash({k: base.get(k, "") for k in CHILD_HASH_FIELDS})
        h_same = generate_hash({k: base.get(k, "") for k in CHILD_HASH_FIELDS})
        self.assertEqual(h_base, h_same)
        
        for field in CHILD_HASH_FIELDS:
            mod = base.copy()
            mod[field] = "CHANGED"
            h_mod = generate_hash({k: mod.get(k, "") for k in CHILD_HASH_FIELDS})
            self.assertNotEqual(h_base, h_mod, f"Hash should change when {field} changes")

    def test_02_overall_status_contract(self):
        # Setup perfect matching sets with a manual blocker (duplicate media) to test READY_FOR_REVIEW
        now = datetime.now(timezone.utc)
        
        source_posts = [
            {"source_post_id": pid, "target_account_id": "liver_manager", "canonical_post_url": f"http://{pid}", "media_count": 2, "updated_at": "2026"}
            for pid in TARGET_SOURCE_POST_IDS
        ]
        
        source_post_media = []
        for pid in TARGET_SOURCE_POST_IDS:
            source_post_media.extend([
                {"source_post_id": pid, "source_post_media_id": f"{pid}_m1", "media_index": 0, "canonical_post_url": f"http://{pid}", "content_hash": "same"},
                {"source_post_id": pid, "source_post_media_id": f"{pid}_m2", "media_index": 0, "canonical_post_url": f"http://{pid}", "content_hash": "same"}
            ])
            
        content_slot_runs = [
            {"slot_run_id": sid, "account_id": "liver_manager", "slot_id": "s1", "status": "CLAIMED", "claim_status": "CLAIMED"}
            for sid in TARGET_SLOT_RUN_IDS
        ]
        
        datasets = {
            "source_posts": source_posts,
            "source_post_media": source_post_media,
            "content_slot_runs": content_slot_runs,
            "queue": [],
            "posted_results": [],
            "media_permissions": [],
            "source_accounts": [],
            "accounts": []
        }
        
        rep = build_repair_plan(
            datasets, 
            verifier_result={"passed": 63, "total": 63, "failed": []}, 
            implementation_head="", 
            origin_main="", 
            now=now
        )
        
        self.assertEqual(rep["overall_status"], "READY_FOR_REVIEW")
        
        # Now introduce a blocker
        source_posts.pop() # Missing one parent
        rep_blocked = build_repair_plan(
            datasets, 
            verifier_result={"passed": 63, "total": 63, "failed": []}, 
            implementation_head="", 
            origin_main="", 
            now=now
        )
        self.assertEqual(rep_blocked["overall_status"], "BLOCKED")
        self.assertIn("PARENT_NOT_FOUND", rep_blocked["parent_repairs"][-1]["blocker_codes"])

    def test_03_asset_relation(self):
        # 1. Any 2 matching signature -> SAME_ASSET
        self.assertEqual(classify_asset_relation([
            {"content_hash": "a"}, {"content_hash": "a"}, {"content_hash": "b"}
        ]), "SAME_ASSET")
        
        # 2. At least 1 signature field present across all rows and all unique -> DISTINCT_ASSET
        self.assertEqual(classify_asset_relation([
            {"content_hash": "a"}, {"content_hash": "b"}
        ]), "DISTINCT_ASSET")
        
        # 3. Otherwise -> UNKNOWN
        self.assertEqual(classify_asset_relation([
            {"content_hash": "a"}, {"media_asset_id": "b"}
        ]), "UNKNOWN")

    def test_04_media_index_sorting(self):
        # Normal
        self.assertEqual(media_index_sort_key(1), (0, 1))
        # Malformed
        self.assertEqual(media_index_sort_key("abc"), (1, "abc"))
        
        unsorted = ["abc", 2, "def", 1, -1]
        s = sorted(unsorted, key=media_index_sort_key)
        self.assertEqual(s, [-1, 1, 2, "abc", "def"])
        
        child_rows = [
            {"source_post_media_id": "1", "media_index": 0, "content_hash": "a", "canonical_post_url": "http://a"},
            {"source_post_media_id": "2", "media_index": 0, "content_hash": "b", "canonical_post_url": "http://a"},
            {"source_post_media_id": "3", "media_index": "malformed", "content_hash": "c", "canonical_post_url": "http://a"},
            {"source_post_media_id": "4", "media_index": "malformed", "content_hash": "d", "canonical_post_url": "http://a"}
        ]
        rep = plan_parent_repair("P1", [{"source_post_id": "P1", "canonical_post_url": "http://a", "media_count": 4}], child_rows)
        # Should correctly assign indices without crashing
        self.assertEqual(rep["unique_media_index_count"], 2)
        ops = [op for op in rep["operations"] if op["operation"] == "SET_MEDIA_INDEX"]
        to_idx = [op["to"] for op in ops]
        self.assertEqual(len(set(to_idx)), len(to_idx))

    def test_05_permission_alignment(self):
        now = datetime.now(timezone.utc)
        def eval_perm(perm_dict):
            base = {"source_id": "src_lm_yt_cand_001", "permission_status": "approved", "rights_status": "approved", "evidence_type": "url", "evidence_reference": "url"}
            base.update(perm_dict)
            blockers = evaluate_external_blockers([], [base], [], now=now)
            return [b["code"] for b in blockers]
            
        self.assertIn("LIVER_PERMISSION_PARTIAL_COVERAGE", eval_perm({"permission_status": "invalid"}))
        self.assertIn("LIVER_PERMISSION_PARTIAL_COVERAGE", eval_perm({"rights_status": "invalid"}))
        self.assertIn("LIVER_PERMISSION_PARTIAL_COVERAGE", eval_perm({"revoked": "true"}))
        self.assertIn("LIVER_PERMISSION_PARTIAL_COVERAGE", eval_perm({"expires_at": "2000-01-01T00:00:00Z"}))
        self.assertIn("LIVER_PERMISSION_PARTIAL_COVERAGE", eval_perm({"expires_at": "malformed"}))
        self.assertIn("LIVER_PERMISSION_PARTIAL_COVERAGE", eval_perm({"evidence_type": ""}))
        self.assertIn("LIVER_PERMISSION_PARTIAL_COVERAGE", eval_perm({"evidence_reference": ""}))
        self.assertNotIn("LIVER_PERMISSION_PARTIAL_COVERAGE", eval_perm({})) # valid

    def test_06_destination_exclusion(self):
        now = datetime.now(timezone.utc)
        
        # Test target ID parsing
        self.assertEqual(parse_target_account_ids('["a", "b"]'), {"a", "b"})
        self.assertEqual(parse_target_account_ids('a|b'), {"a", "b"})
        self.assertEqual(parse_target_account_ids('a,b'), {"a", "b"})
        self.assertEqual(parse_target_account_ids('liver_manager'), {"liver_manager"})
        self.assertEqual(parse_target_account_ids('not_liver_manager'), {"not_liver_manager"})
        
        accs = [{"threads_handle": "my_dest"}]
        source = {
            "target_account_ids": "liver_manager",
            "platform": "threads",
            "active": "true",
            "source_url": "https://threads.net/@my_dest",
            "review_status": "APPROVED"
        }
        b = evaluate_external_blockers([source], [], accs, now=now)
        # Should be excluded, so MISSING
        codes = [x["code"] for x in b]
        self.assertIn("LIVER_THREADS_SOURCE_MISSING", codes)
        
        source["source_url"] = "https://threads.net/@other"
        b2 = evaluate_external_blockers([source], [], accs, now=now)
        codes2 = [x["code"] for x in b2]
        self.assertNotIn("LIVER_THREADS_SOURCE_MISSING", codes2)

    def test_07_mock_safety_early_abort(self):
        from unittest.mock import patch
        import plan_wp3c_production_repairs
        
        with tempfile.NamedTemporaryFile(delete=False) as f:
            out_path = f.name
            
        old_argv = sys.argv
        sys.argv = ["plan_wp3c_production_repairs.py", "--output", out_path]
        
        # Ensure config_loader is not in sys.modules
        if "config_loader" in sys.modules:
            del sys.modules["config_loader"]
            
        with patch("plan_wp3c_production_repairs.check_safety_flags", return_value=True):
            try:
                with self.assertRaises(SystemExit) as e:
                    plan_wp3c_production_repairs.main()
                self.assertEqual(e.exception.code, 1)
            finally:
                sys.argv = old_argv
                if os.path.exists(out_path): os.remove(out_path)
                
        # Assert it was never imported
        self.assertNotIn("config_loader", sys.modules)

    def test_08_write_bomb(self):
        class FakeClient:
            def __init__(self):
                self.calls = {m: 0 for m in [
                    "_ensure_tab", "append_row", "append_rows", "update", "update_cell",
                    "batch_update", "resize", "clear", "delete_rows", "setup_all", "seed", "save"
                ]}
            def get_all_records(self): return []
            def _ws(self, name): return self
            
            # Write methods
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
        
        # Test full read path using protected client
        missing = []
        datasets = {}
        for t in ["source_posts", "source_post_media"]:
            try:
                ws = client._ws(t)
                prevent_writes(ws)
                datasets[t] = [dict(r) for r in ws.get_all_records()]
            except Exception as e:
                pass
                
        for m, count in client.calls.items():
            self.assertEqual(count, 0, f"Method {m} was called {count} times")
            
        with self.assertRaises(Exception):
            client.update()

    # Slot tests broken down
    def test_09_slot_post_url(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "post_url": "http"}], {}, {}, now=now)
        self.assertEqual(rev["recommendation"], "NO_ACTION_POST_EVIDENCE_PRESENT")

    def test_09_slot_result_posted(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "result_id": "R"}], {}, {"R": {"status": "POSTED"}}, now=now)
        self.assertEqual(rev["recommendation"], "NO_ACTION_POST_EVIDENCE_PRESENT")
        
    def test_09_slot_result_recovered(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "result_id": "R"}], {}, {"R": {"status": "RECOVERED"}}, now=now)
        self.assertEqual(rev["recommendation"], "NO_ACTION_POST_EVIDENCE_PRESENT")

    def test_09_slot_queue_posted(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "queue_id": "Q"}], {"Q": {"status": "POSTED"}}, {}, now=now)
        self.assertEqual(rev["recommendation"], "NO_ACTION_POST_EVIDENCE_PRESENT")

    def test_09_slot_queue_posted_save_failed(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "queue_id": "Q"}], {"Q": {"status": "POSTED_SAVE_FAILED"}}, {}, now=now)
        self.assertEqual(rev["recommendation"], "NO_ACTION_POST_EVIDENCE_PRESENT")

    def test_09_slot_status_posted_primary(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "status": "POSTED_PRIMARY"}], {}, {}, now=now)
        self.assertEqual(rev["recommendation"], "NO_ACTION_POST_EVIDENCE_PRESENT")
        
    def test_09_slot_status_posted_fallback(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "status": "POSTED_FALLBACK"}], {}, {}, now=now)
        self.assertEqual(rev["recommendation"], "NO_ACTION_POST_EVIDENCE_PRESENT")
        
    def test_09_slot_status_backfilled(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "status": "BACKFILLED"}], {}, {}, now=now)
        self.assertEqual(rev["recommendation"], "NO_ACTION_POST_EVIDENCE_PRESENT")

    def test_09_slot_expired_status(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "status": "CLAIMED", "lease_expires_at": "2000-01-01T00:00:00Z"}], {}, {}, now=now)
        self.assertEqual(rev["recommendation"], "ELIGIBLE_TO_MARK_RECOVERY_REQUIRED")

    def test_09_slot_expired_claim_status(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "status": "OTHER", "claim_status": "CLAIMED", "lease_expires_at": "2000-01-01T00:00:00Z"}], {}, {}, now=now)
        self.assertEqual(rev["recommendation"], "ELIGIBLE_TO_MARK_RECOVERY_REQUIRED")

    def test_09_slot_future_active_lease(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "status": "CLAIMED", "lease_expires_at": "2099-01-01T00:00:00Z"}], {}, {}, now=now)
        self.assertEqual(rev["recommendation"], "MANUAL_REVIEW")

    def test_09_slot_recovery_required(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "status": "RECOVERY_REQUIRED"}], {}, {}, now=now)
        self.assertEqual(rev["recommendation"], "ALREADY_RECOVERY_REQUIRED")

    def test_09_slot_malformed_lease(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "status": "CLAIMED", "lease_expires_at": "malformed"}], {}, {}, now=now)
        self.assertIn("LEASE_TIMESTAMP_INVALID", rev["blocker_codes"])
        self.assertEqual(rev["recommendation"], "MANUAL_REVIEW")

    def test_09_slot_naive_lease(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "status": "CLAIMED", "lease_expires_at": "2000-01-01T00:00:00"}], {}, {}, now=now)
        self.assertEqual(rev["recommendation"], "ELIGIBLE_TO_MARK_RECOVERY_REQUIRED")

    def test_09_slot_z_lease(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "status": "CLAIMED", "lease_expires_at": "2000-01-01T00:00:00Z"}], {}, {}, now=now)
        self.assertEqual(rev["recommendation"], "ELIGIBLE_TO_MARK_RECOVERY_REQUIRED")

    def test_09_slot_timezone_lease(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S", "status": "CLAIMED", "lease_expires_at": "2000-01-01T00:00:00+09:00"}], {}, {}, now=now)
        self.assertEqual(rev["recommendation"], "ELIGIBLE_TO_MARK_RECOVERY_REQUIRED")

    def test_09_slot_missing(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [], {}, {}, now=now)
        self.assertIn("SLOT_NOT_FOUND", rev["blocker_codes"])

    def test_09_slot_duplicate(self):
        now = datetime.now(timezone.utc)
        rev = plan_stale_slot_review("S", [{"slot_run_id": "S"}, {"slot_run_id": "S"}], {}, {}, now=now)
        self.assertIn("MULTIPLE_SLOTS", rev["blocker_codes"])

    def test_09_slot_hash_stability(self):
        now = datetime.now(timezone.utc)
        rev1 = plan_stale_slot_review("S", [{"slot_run_id": "S", "a": 1}], {}, {}, now=now)
        rev2 = plan_stale_slot_review("S", [{"slot_run_id": "S", "a": 1}], {}, {}, now=now)
        self.assertEqual(rev1["precondition_hash"], rev2["precondition_hash"])
        
        rev3 = plan_stale_slot_review("S", [{"slot_run_id": "S", "a": 2}], {}, {}, now=now)
        self.assertNotEqual(rev1["precondition_hash"], rev3["precondition_hash"])

    def test_10_redaction_full(self):
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
            "content_slot_runs": [{"slot_run_id": TARGET_SLOT_RUN_IDS[0], "post_text": "TEST_POST_TEXT_SECRET", "transcript": "TEST_TRANSCRIPT_SECRET"}],
            "queue": [],
            "posted_results": [],
            "media_permissions": [{"source_id": "src_lm_yt_cand_001", "permission_status": "approved", "rights_status": "approved", "evidence_type": "url", "evidence_reference": "TEST_PERMISSION_EVIDENCE_SECRET", "approved_by": "TEST_APPROVED_BY_SECRET", "notes": "TEST_NOTES_SECRET"}],
            "source_accounts": [{"target_account_ids": "liver_manager", "platform": "threads", "active": "true", "source_url": "TEST_SOURCE_URL_SECRET", "review_status": "APPROVED", "access_token": "TEST_ACCESS_TOKEN_SECRET"}],
            "accounts": []
        }
        
        rep = build_repair_plan(datasets, verifier_result={"passed": 63, "total": 63, "failed": []}, implementation_head="", origin_main="", now=now)
        rep_str = json.dumps(rep)
        
        for sv in secret_vals:
            self.assertNotIn(sv, rep_str, f"Secret {sv} leaked in plan JSON")

if __name__ == '__main__':
    unittest.main()
