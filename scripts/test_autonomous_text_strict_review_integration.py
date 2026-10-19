#!/usr/bin/env python3
"""Offline integration: V2 editorial drafts remain held; legacy text requires Hybrid AI."""
from __future__ import annotations
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"scripts")]
import auto_approve_queue as approval
import generate_threads_ideas_from_references as generator

ACCOUNTS=("night_scout","liver_manager","beauty_account")
def sample_rows(account: str)->dict:
    with patch.object(generator,"generate_production_post",side_effect=AssertionError("NETWORK_GENERATION_FORBIDDEN")):
        batch=generator.build_fallback_generation_rows(
            account_id=account,top_n=1,offline_original=True,post_type="original_text",
            slot_id="safe_offline_test",schedule_date_jst="2026-10-20")
    if len(batch["queue"])!=1: raise AssertionError("expected_one_valid_offline_candidate")
    return batch

def evaluate(batch:dict,account:str)->dict:
    rules={**approval.rules_for_account(approval.load_rules(),account),"auto_ready_enabled":True}
    return approval.evaluate_item(queue=batch["queue"][0],draft=batch["drafts"][0],
        derivative=batch["social_derivatives"][0],scores_by_ref={},existing_texts=[],rules=rules)

class StrictAutonomousTextReviewTests(unittest.TestCase):
    def test_default_v2_stays_draft_only_three_accounts(self):
        for account in ACCOUNTS:
            with self.subTest(account=account):
                batch=sample_rows(account);row=batch["queue"][0]
                self.assertEqual(row["status"],"WAITING_REVIEW")
                self.assertEqual(row["content_quality_v2_status"],"DRAFT_ONLY_RANKED")
                self.assertEqual(evaluate(batch,account)["status"],"DRAFT_ONLY")
                self.assertEqual(row["route_status"],"DRAFT_ONLY")

    def test_strict_legacy_text_still_needs_hybrid_and_no_direct_ready(self):
        for account in ACCOUNTS:
            with self.subTest(account=account):
                batch=sample_rows(account);row=batch["queue"][0]
                self.assertEqual(generator._admit_autonomous_text_review_rows(batch,account),1)
                self.assertEqual(row["status"],"WAITING_REVIEW")
                self.assertEqual(row["auto_publish"],"false")
                self.assertEqual(row["route_status"],"AUTONOMOUS_TEXT_STRICT_REVIEW_PENDING")
                self.assertEqual(row["content_quality_v2_status"],"")
                self.assertEqual(row["content_quality_v2_version"],"")
                blocked=evaluate(batch,account)
                self.assertEqual(blocked["status"],"REJECTED")
                self.assertIn("hybrid_ai_gate_missing",blocked["reasons"])
                with patch.object(approval,"hybrid_ai_gate_passed",return_value=(True,"")):
                    permitted=evaluate(batch,account)
                self.assertEqual(permitted["status"],"APPROVABLE")
                self.assertEqual(permitted["reasons"],[])
                self.assertEqual(row["status"],"WAITING_REVIEW")

    def test_media_identity_and_approval_scope_refused(self):
        cases=(("other_account",{"target_account_id":"other"}),
            ("x_platform",{"platform":"x"}),("media_required",{"media_required":"true"}),
            ("media_asset",{"media_asset_id":"asset"}),("clip",{"video_clip_id":"clip"}),
            ("permission",{"permission_status":"unknown"}),("rights",{"rights_status":"unknown"}),
            ("review_needed",{"rights_review_required":"true"}),
            ("already_ready",{"status":"READY"}),
            ("unexpected_origin",{"content_quality_v2_status":"ALREADY_READY"}))
        for label,fields in cases:
            with self.subTest(label=label):
                batch=sample_rows("night_scout");batch["queue"][0].update(fields)
                with self.assertRaises(ValueError):
                    generator._admit_autonomous_text_review_rows(batch,"night_scout")
                self.assertEqual(batch["queue"][0].get("content_quality_v2_version"),"content_quality_v2")

    def test_validator_and_generation_hard_gates_stay_draft(self):
        batch=sample_rows("liver_manager")
        with patch.object(generator,"final_public_post_validator",return_value={"status":"BLOCKED"}):
            self.assertEqual(generator._admit_autonomous_text_review_rows(batch,"liver_manager"),0)
        self.assertEqual(batch["queue"][0]["content_quality_v2_status"],"DRAFT_ONLY_RANKED")
        batch=sample_rows("night_scout")
        batch["queue"][0]["hard_gate_reasons"]='["fabricated_personal_experience"]'
        self.assertEqual(generator._admit_autonomous_text_review_rows(batch,"night_scout"),0)
        self.assertEqual(batch["queue"][0]["route_status"],"DRAFT_ONLY")

    def test_provenance_cannot_be_reused_or_crossed(self):
        batch=sample_rows("night_scout")
        batch["queue"][0]["content_quality_v2_version"]="unexpected"
        with self.assertRaises(ValueError):
            generator._admit_autonomous_text_review_rows(batch,"night_scout")
        batch=sample_rows("night_scout")
        with self.assertRaises(ValueError):
            generator._admit_autonomous_text_review_rows(batch,"liver_manager")
        batch=sample_rows("beauty_account")
        saved=copy.deepcopy(batch["queue"][0])
        self.assertEqual(generator._admit_autonomous_text_review_rows(batch,"beauty_account"),1)
        with self.assertRaises(ValueError):
            generator._admit_autonomous_text_review_rows(batch,"beauty_account")
        self.assertEqual(batch["queue"][0]["status"],"WAITING_REVIEW")
        self.assertEqual(saved["content_quality_v2_status"],"DRAFT_ONLY_RANKED")

if __name__=="__main__":
    unittest.main()
