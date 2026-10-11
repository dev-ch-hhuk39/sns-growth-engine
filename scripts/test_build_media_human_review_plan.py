#!/usr/bin/env python3
"""Offline safety regression for the Phase 5B-1 media review plan."""
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_media_human_review_plan import build_plan  # noqa: E402


def fixture() -> dict:
    slots = [
        ("night_scout", "ns_1800_direct_media", "direct_reference_media"),
        ("night_scout", "ns_2100_clip_media", "approved_source_clip"),
        ("liver_manager", "lm_1600_direct_media", "direct_reference_media"),
        ("liver_manager", "lm_1800_clip_media", "approved_source_clip"),
    ]
    media_slots = [
        {
            "account_id": account, "slot_id": slot, "post_type": post_type,
            "queue": {"exact_candidates": [], "recent_account_media_when_exact_missing": []},
        }
        for account, slot, post_type in slots
    ]
    return {
        "status": "AUDIT_COMPLETE", "would_post": False, "writes_performed": False,
        "protected_rows_unchanged_during_audit": True,
        "protected_required_values_all_match": True,
        "media_slots": media_slots,
    }


def approved_clip(queue_id: str = "clip_001") -> dict:
    return {
        "queue_id": queue_id, "status": "READY",
        "rights_status": "APPROVED", "permission_status": "APPROVED",
        "validator_status": "PASS", "internal_leak_status": "PASS",
        "account_fit_status": "PASS", "alignment_status": "PASS",
        "hybrid_ai_status": "PASS", "quality_review": {"pass": True},
        "media_asset_id": "asset_1",
        "clip_contract": {
            "clip_candidate_present": True, "source_video_present": True,
            "duration_in_review_range_8_to_45_seconds": True,
            "evidence_present": True,
        },
    }


class ReviewPlannerTests(unittest.TestCase):
    def test_empty_slots_create_review_work_without_promoting_other_media(self):
        audit = fixture()
        audit["media_slots"][0]["queue"]["recent_account_media_when_exact_missing"] = [{}, {}]
        report = build_plan(audit)
        self.assertEqual(report["slot_count"], 4)
        self.assertEqual(report["review_item_count"], 4)
        self.assertEqual(report["priority_counts"], {"P1": 4, "P2": 0, "P3": 0})
        item = next(row for row in report["items"] if row["slot_id"] == "ns_1800_direct_media")
        self.assertEqual(item["other_slot_candidates_not_promoted"], 2)
        self.assertEqual(item["review_state"], "MISSING_EXACT_CANDIDATE")
        self.assertEqual(item["queue_id"], "")
        self.assertFalse(report["publish_authorized"])
        self.assertFalse(report["ready_transitions_performed"])

    def test_even_fully_approved_metadata_cannot_authorize_publishing(self):
        audit = fixture()
        audit["media_slots"][3]["queue"]["exact_candidates"] = [approved_clip()]
        result = build_plan(audit)
        clip = next(row for row in result["items"] if row["queue_id"] == "clip_001")
        self.assertEqual(clip["blockers"], [])
        self.assertEqual(clip["review_state"], "FINAL_HUMAN_REVIEW_REQUIRED")
        self.assertEqual(clip["priority"], "P3")
        self.assertTrue(clip["human_approval_required"])
        self.assertFalse(clip["publish_authorized"])

    def test_rights_and_missing_clip_evidence_have_high_priority(self):
        audit = fixture()
        item = approved_clip()
        item.update(rights_status="DENIED", permission_status="", media_asset_id="",
                    clip_contract={"source_video_present": True})
        audit["media_slots"][3]["queue"]["exact_candidates"] = [item]
        result = build_plan(audit)
        clip = next(row for row in result["items"] if row["queue_id"] == "clip_001")
        self.assertEqual(clip["priority"], "P1")
        for reason in (
            "rights_human_verification_required", "permission_human_verification_required",
            "prepared_media_missing", "clip_candidate_evidence_missing",
            "clip_duration_unverified", "clip_evidence_map_missing",
        ):
            self.assertIn(reason, clip["blockers"])

    def test_direct_media_requires_original_source_evidence(self):
        audit = fixture()
        item = approved_clip()
        item.update(queue_id="direct_1", direct_reuse_contract={
            "source_identity_present": False, "source_text_available_for_reuse_check": False,
        })
        audit["media_slots"][0]["queue"]["exact_candidates"] = [item]
        result = build_plan(audit)
        row = next(row for row in result["items"] if row["queue_id"] == "direct_1")
        self.assertIn("original_source_identity_missing", row["blockers"])
        self.assertIn("source_text_comparison_unavailable", row["blockers"])

    def test_raw_captions_urls_secrets_and_transcripts_are_never_exported(self):
        audit = fixture()
        item = approved_clip()
        item.update(public_post_text="SECRET_CAPTION", source_url="SECRET_URL",
                    transcript_excerpt="SECRET_TRANSCRIPT", api_key="SECRET_TOKEN")
        audit["media_slots"][3]["queue"]["exact_candidates"] = [item]
        result = json.dumps(build_plan(audit), ensure_ascii=False)
        for word in ("SECRET_CAPTION", "SECRET_URL", "SECRET_TRANSCRIPT", "SECRET_TOKEN"):
            self.assertNotIn(word, result)

    def test_invalid_identifier_is_not_echoed(self):
        audit = fixture()
        audit["media_slots"][3]["queue"]["exact_candidates"] = [
            approved_clip("unsafe_content\nPRIVATE_TEXT")
        ]
        result = build_plan(audit)
        row = next(row for row in result["items"] if row["slot_id"] == "lm_1800_clip_media")
        self.assertEqual(row["queue_id"], "")
        self.assertIn("queue_identifier_unverifiable", row["blockers"])
        self.assertNotIn("PRIVATE_TEXT", json.dumps(result))

    def test_tampered_or_incomplete_read_only_report_is_rejected(self):
        audit = fixture()
        for name, value in (
            ("status", "AUDIT_FAILED"),
            ("would_post", True),
            ("writes_performed", True),
            ("protected_rows_unchanged_during_audit", False),
            ("protected_required_values_all_match", False),
        ):
            modified = copy.deepcopy(audit)
            modified[name] = value
            with self.subTest(name=name), self.assertRaisesRegex(
                ValueError, "audit_safety_invariants_not_verified"
            ):
                build_plan(modified)
        modified = fixture()
        modified["media_slots"].pop()
        with self.assertRaisesRegex(ValueError, "media_slot_set_incomplete"):
            build_plan(modified)

    def test_duplicate_or_incorrect_slot_is_rejected(self):
        audit = fixture()
        audit["media_slots"][0]["slot_id"] = "lm_1800_clip_media"
        with self.assertRaisesRegex(ValueError, "media_slot_identity_invalid"):
            build_plan(audit)

    def test_candidate_count_is_bounded_and_never_changes_queue(self):
        audit = fixture()
        audit["media_slots"][3]["queue"]["exact_candidates"] = [
            approved_clip(f"clip_{i}") for i in range(100)
        ]
        report = build_plan(audit)
        matching = [x for x in report["items"] if x["slot_id"] == "lm_1800_clip_media"]
        self.assertEqual(len(matching), 5)
        self.assertFalse(report["writes_performed"])
        self.assertEqual(report["status"], "HUMAN_REVIEW_REQUIRED")


if __name__ == "__main__":
    unittest.main()
