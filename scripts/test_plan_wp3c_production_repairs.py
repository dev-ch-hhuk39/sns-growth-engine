import unittest
import os
import json
import tempfile
import subprocess
from datetime import datetime, timezone

class TestWP3CRepairPlanner(unittest.TestCase):
    def run_planner(self, env_updates=None, extra_args=None):
        env = os.environ.copy()
        if env_updates:
            env.update(env_updates)
        with tempfile.NamedTemporaryFile(delete=False) as f:
            out_path = f.name
        
        cmd = ["python3", "scripts/plan_wp3c_production_repairs.py", "--output", out_path]
        if extra_args:
            cmd.extend(extra_args)
            
        res = subprocess.run(cmd, env=env, capture_output=True, text=True)
        
        data = {}
        if os.path.exists(out_path):
            with open(out_path, "r") as f:
                try:
                    data = json.load(f)
                except: pass
            os.remove(out_path)
        return res, data

    def test_01_02_14_write_bomb(self):
        from plan_wp3c_production_repairs import prevent_writes
        class FakeClient:
            def update(self): pass
            def update_cell(self): pass
            def batch_update(self): pass
            def _ensure_tab(self): pass
            def append_row(self): pass
            def append_rows(self): pass
            def resize(self): pass
            def clear(self): pass
            def delete_rows(self): pass
            def setup_all(self): pass
            def seed(self): pass
            def save(self): pass
        
        client = FakeClient()
        prevent_writes(client)
        methods = [
            "_ensure_tab", "append_row", "append_rows", "update", "update_cell",
            "batch_update", "resize", "clear", "delete_rows", "setup_all", "seed", "save"
        ]
        for m in methods:
            with self.assertRaises(Exception) as ctx:
                getattr(client, m)()
            self.assertIn("WRITE BOMB TRIGGERED", str(ctx.exception))

    def test_03_13_safety_flag_true(self):
        res, data = self.run_planner(env_updates={"PUBLISH_ENABLED": "true"})
        self.assertEqual(res.returncode, 1)
        self.assertEqual(data.get("overall_status"), "FAIL")
        self.assertIn("SAFETY_FLAG_TRUE", data.get("status_reasons", []))
        self.assertIn("WP3C_SAFE_REPAIR_PLAN_JSON=", res.stdout)
        
        # Test 13: Mock check in safety
        from unittest.mock import patch
        with patch("plan_wp3c_production_repairs.check_safety_flags", return_value=True):
            
            with tempfile.NamedTemporaryFile(delete=False) as f:
                out_path = f.name
            
            import sys
            import plan_wp3c_production_repairs
            old_argv = sys.argv
            sys.argv = ["plan_wp3c_production_repairs.py", "--output", out_path]
            try:
                with self.assertRaises(SystemExit) as e:
                    plan_wp3c_production_repairs.main()
                self.assertEqual(e.exception.code, 1)
            finally:
                sys.argv = old_argv
                if os.path.exists(out_path): os.remove(out_path)

    def test_04_05_06_exit_codes(self):
        from plan_wp3c_production_repairs import build_repair_plan
        now = datetime.now(timezone.utc)
        rep_blocked = build_repair_plan(
            {}, verifier_result={"failed": [1]}, implementation_head="", origin_main="", now=now
        )
        self.assertEqual(rep_blocked["overall_status"], "FAIL")
        
        rep_ok = build_repair_plan(
            {
                "source_posts": [{"source_post_id": pid, "canonical_post_url": "http://a", "media_count": 0} for pid in [
                    "sp_src_lm_yt_user_001_UCzFzty7aEd4tw3NqCW6pkLQ",
                    "sp_src_ns_threads_user_chiishunin_s_DbAmx0dEjy3",
                    "sp_src_ns_threads_user_chiishunin_s_Da8Jwc6kiAf",
                    "sp_src_ns_threads_required_002_DSSq-YaE6TC"
                ]],
                "source_accounts": [{"target_account_id": "liver_manager", "platform": "threads", "active": "true", "source_url": "http://a", "review_status": "APPROVED"}],
                "media_permissions": [{"source_id": "src_lm_yt_cand_001", "permission_status": "approved", "rights_status": "approved", "evidence_type": "url", "evidence_reference": "url"}]
            }, verifier_result={"passed": 63, "total": 63, "failed": []}, implementation_head="", origin_main="", now=now
        )
        self.assertEqual(rep_ok["overall_status"], "BLOCKED") # missing slots

    def test_07_08_cli_strictness(self):
        prohibited = ["--apply", "--apply=true", "--confirm", "--write", "--repair", "--update", "--account-id", "some_id", "--source-post-id", "some_id", "--unknown"]
        for p in prohibited:
            res, _ = self.run_planner(extra_args=[p])
            self.assertEqual(res.returncode, 2)

    def test_09_to_11_parent_missing_duplicate(self):
        from plan_wp3c_production_repairs import plan_parent_repair
        rep_missing = plan_parent_repair("A", [], [])
        self.assertIn("PARENT_NOT_FOUND", rep_missing["blocker_codes"])
        self.assertFalse(rep_missing["apply_eligible"])
        
        rep_dup = plan_parent_repair("A", [{"source_post_id": "A"}, {"source_post_id": "A"}], [])
        self.assertIn("MULTIPLE_PARENTS", rep_dup["blocker_codes"])
        self.assertFalse(rep_dup["apply_eligible"])
        
        rep_ok = plan_parent_repair("A", [{"source_post_id": "A", "canonical_post_url": "http://a", "media_count": 0}], [])
        self.assertNotIn("PARENT_NOT_FOUND", rep_ok["blocker_codes"])

    def test_12_13_child_id(self):
        from plan_wp3c_production_repairs import plan_parent_repair
        rep = plan_parent_repair("A", [{"source_post_id": "A", "canonical_post_url": "http://a", "media_count": 1}], [{"media_index": 0}])
        self.assertIn("CHILD_ID_MISSING", rep["blocker_codes"])
        
        rep_dup = plan_parent_repair("A", [{"source_post_id": "A", "canonical_post_url": "http://a", "media_count": 2}], [{"source_post_media_id": "C1", "media_index": 0, "canonical_post_url": "http://a"}, {"source_post_media_id": "C1", "media_index": 1, "canonical_post_url": "http://a"}])
        self.assertIn("DUPLICATE_CHILD_ID", rep_dup["blocker_codes"])

    def test_14_to_16_canonical(self):
        from plan_wp3c_production_repairs import plan_parent_repair
        rep1 = plan_parent_repair("A", [{"source_post_id": "A", "canonical_post_url": "", "media_count": 0}], [])
        self.assertIn("PARENT_CANONICAL_URL_MISSING", rep1["blocker_codes"])
        
        rep2 = plan_parent_repair("A", [{"source_post_id": "A", "canonical_post_url": "http://a", "media_count": 1}], [{"source_post_media_id": "C1", "canonical_post_url": "", "media_index": 0}])
        self.assertIn("CHILD_CANONICAL_URL_MISSING", rep2["blocker_codes"])
        self.assertFalse(rep2["apply_eligible"])
        
        rep3 = plan_parent_repair("A", [{"source_post_id": "A", "canonical_post_url": "http://a", "media_count": 1}], [{"source_post_media_id": "C1", "canonical_post_url": "http://b", "media_index": 0}])
        ops = [op["operation"] for op in rep3["operations"]]
        self.assertIn("SET_CHILD_CANONICAL_URL_FROM_PARENT", ops)
        self.assertTrue(rep3["apply_eligible"])

    def test_17_to_22_media_count_and_index(self):
        from plan_wp3c_production_repairs import plan_parent_repair
        rep1 = plan_parent_repair("A", [{"source_post_id": "A", "canonical_post_url": "http://a", "media_count": 1}], [{"source_post_media_id": "C1", "canonical_post_url": "http://a", "media_index": -1}])
        self.assertIn("NEGATIVE_MEDIA_INDEX", rep1["blocker_codes"])
        
        rep2 = plan_parent_repair("A", [{"source_post_id": "A", "canonical_post_url": "http://a", "media_count": 1}], [{"source_post_media_id": "C1", "canonical_post_url": "http://a", "media_index": "abc"}])
        self.assertIn("MALFORMED_MEDIA_INDEX", rep2["blocker_codes"])
        
        rep3 = plan_parent_repair("A", [{"source_post_id": "A", "canonical_post_url": "http://a", "media_count": -1}], [])
        self.assertIn("NEGATIVE_PARENT_MEDIA_COUNT", rep3["blocker_codes"])
        
        rep4 = plan_parent_repair("A", [{"source_post_id": "A", "canonical_post_url": "http://a", "media_count": "abc"}], [])
        self.assertIn("MALFORMED_PARENT_MEDIA_COUNT", rep4["blocker_codes"])
        
        rep5 = plan_parent_repair("A", [{"source_post_id": "A", "canonical_post_url": "http://a", "media_count": 1}], [{"source_post_media_id": "C1", "canonical_post_url": "http://a", "media_index": 0}, {"source_post_media_id": "C2", "canonical_post_url": "http://a", "media_index": 1}])
        ops = [op["operation"] for op in rep5["operations"]]
        self.assertIn("SET_PARENT_MEDIA_COUNT", ops)

    def test_23_to_26_duplicate_asset_classification(self):
        from plan_wp3c_production_repairs import classify_asset_relation
        self.assertEqual(classify_asset_relation([{"content_hash": "a"}, {"content_hash": "a"}]), "SAME_ASSET")
        self.assertEqual(classify_asset_relation([{"content_hash": "a"}, {"content_hash": "b"}]), "DISTINCT_ASSET")
        self.assertEqual(classify_asset_relation([{"content_hash": ""}, {"content_hash": ""}]), "UNKNOWN")
        self.assertEqual(classify_asset_relation([{"content_hash": "a"}, {"content_hash": "a"}, {"content_hash": "b"}]), "SAME_ASSET") # Manual blocker

    def test_27_to_31_index_reassignment(self):
        from plan_wp3c_production_repairs import plan_parent_repair
        childs = [
            {"source_post_media_id": "C1", "media_index": 0, "content_hash": "a", "canonical_post_url": "http://a"},
            {"source_post_media_id": "C2", "media_index": 0, "content_hash": "b", "canonical_post_url": "http://a"},
            {"source_post_media_id": "C3", "media_index": 2, "content_hash": "c", "canonical_post_url": "http://a"},
            {"source_post_media_id": "C4", "media_index": 2, "content_hash": "d", "canonical_post_url": "http://a"}
        ]
        rep = plan_parent_repair("A", [{"source_post_id": "A", "canonical_post_url": "http://a", "media_count": 4}], childs)
        ops = [op for op in rep["operations"] if op["operation"] == "SET_MEDIA_INDEX"]
        self.assertEqual(len(ops), 2)
        to_indices = set(op["to"] for op in ops)
        self.assertTrue(to_indices.issubset({1, 3, 4})) # 0 and 2 are used
        self.assertEqual(len(to_indices), 2)
        
    def test_32_to_35_hash_stability(self):
        from plan_wp3c_production_repairs import generate_hash
        h1 = generate_hash({"a": 1, "b": 2})
        h2 = generate_hash({"b": 2, "a": 1})
        self.assertEqual(h1, h2)
        
        h3 = generate_hash({"a": 1, "b": 3})
        self.assertNotEqual(h1, h3)

    def test_36_to_48_slot_logic(self):
        from plan_wp3c_production_repairs import plan_stale_slot_review
        now = datetime.now(timezone.utc)
        
        # 36. post_url
        rev1 = plan_stale_slot_review("S", [{"slot_run_id": "S", "post_url": "http://a"}], {}, {}, now=now)
        self.assertEqual(rev1["recommendation"], "NO_ACTION_POST_EVIDENCE_PRESENT")
        
        # 41. expired claim
        rev2 = plan_stale_slot_review("S", [{"slot_run_id": "S", "status": "CLAIMED", "lease_expires_at": "2000-01-01T00:00:00Z"}], {}, {}, now=now)
        self.assertEqual(rev2["recommendation"], "ELIGIBLE_TO_MARK_RECOVERY_REQUIRED")
        
        # 44. malformed lease
        rev3 = plan_stale_slot_review("S", [{"slot_run_id": "S", "status": "CLAIMED", "lease_expires_at": "abc"}], {}, {}, now=now)
        self.assertIn("LEASE_TIMESTAMP_INVALID", rev3["blocker_codes"])
        self.assertEqual(rev3["recommendation"], "MANUAL_REVIEW")

    def test_49_to_56_external_blockers(self):
        from plan_wp3c_production_repairs import evaluate_external_blockers
        now = datetime.now(timezone.utc)
        
        b1 = evaluate_external_blockers([], [], now=now)
        codes = [b["code"] for b in b1]
        self.assertIn("LIVER_THREADS_SOURCE_MISSING", codes)
        self.assertIn("LIVER_PERMISSION_PARTIAL_COVERAGE", codes)
        
        accs = [{"target_account_id": "liver_manager", "platform": "threads", "active": "true", "source_url": "http://a", "review_status": "APPROVED"}]
        perms = [{"source_id": "src_lm_yt_cand_001", "permission_status": "approved", "rights_status": "approved", "evidence_type": "url", "evidence_reference": "url"}]
        b2 = evaluate_external_blockers(accs, perms, now=now)
        self.assertEqual(len(b2), 0)
        
        perms2 = [{"source_id": "src_lm_yt_cand_001", "permission_status": "approved", "rights_status": "approved", "evidence_type": "url", "evidence_reference": "url", "revoked": "true"}]
        b3 = evaluate_external_blockers(accs, perms2, now=now)
        codes3 = [b["code"] for b in b3]
        self.assertIn("LIVER_PERMISSION_PARTIAL_COVERAGE", codes3)

    def test_57_to_65_redaction_and_schema(self):
        from plan_wp3c_production_repairs import build_failure_report, plan_parent_repair, plan_stale_slot_review, evaluate_external_blockers
        now = datetime.now(timezone.utc)
        
        rep = build_failure_report("UNEXPECTED_EXCEPTION")
        self.assertEqual(rep["schema_version"], 1)
        self.assertIn("safety", rep)
        
        # Test fixture redaction
        secret = "TEST_SECRET_VALUE"
        
        rep_p = plan_parent_repair("A", [{"source_post_id": "A", "canonical_post_url": "http://a", "media_count": 0}], [{"source_post_media_id": "C", "canonical_post_url": secret}])
        rep_str = json.dumps(rep_p)
        self.assertNotIn(secret, rep_str) # Child canonical mismatch uses pre-set operations without printing the secret URL directly
        
        accs = [{"target_account_id": "liver_manager", "platform": "threads", "active": "true", "source_url": secret, "review_status": "APPROVED"}]
        perms = [{"source_id": "src_lm_yt_cand_001", "permission_status": "approved", "rights_status": "approved", "evidence_type": "url", "evidence_reference": secret, "notes": secret}]
        b = evaluate_external_blockers(accs, perms, now=now)
        b_str = json.dumps(b)
        self.assertNotIn(secret, b_str)

def run_all():
    unittest.main()

if __name__ == '__main__':
    run_all()
