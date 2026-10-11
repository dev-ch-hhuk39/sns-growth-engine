#!/usr/bin/env python3
"""Regression tests for non-authoritative Phase 5B-2 review receipts."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_media_human_review_plan import build_plan  # noqa: E402
from build_media_review_approval_receipts import (  # noqa: E402
    ReviewContractError, _sha256, build_receipts,
)

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


def sample_plan(*, eligible_clip: bool = True) -> dict:
    slots = [
        ("night_scout", "ns_1800_direct_media", "direct_reference_media"),
        ("night_scout", "ns_2100_clip_media", "approved_source_clip"),
        ("liver_manager", "lm_1600_direct_media", "direct_reference_media"),
        ("liver_manager", "lm_1800_clip_media", "approved_source_clip"),
    ]
    audit = {
        "status": "AUDIT_COMPLETE",
        "would_post": False, "writes_performed": False,
        "protected_rows_unchanged_during_audit": True,
        "protected_required_values_all_match": True,
        "media_slots": [
            {
                "account_id": account, "slot_id": slot, "post_type": post_type,
                "queue": {"exact_candidates": [], "recent_account_media_when_exact_missing": []},
            }
            for account, slot, post_type in slots
        ],
    }
    if eligible_clip:
        audit["media_slots"][3]["queue"]["exact_candidates"] = [{
            "queue_id": "clip_001", "status": "READY",
            "rights_status": "APPROVED", "permission_status": "APPROVED",
            "validator_status": "PASS", "internal_leak_status": "PASS",
            "account_fit_status": "PASS", "alignment_status": "PASS",
            "hybrid_ai_status": "PASS", "quality_review": {"pass": True},
            "media_asset_id": "media_asset_001",
            "clip_contract": {
                "clip_candidate_present": True, "source_video_present": True,
                "duration_in_review_range_8_to_45_seconds": True,
                "evidence_present": True,
            },
        }]
    return build_plan(audit)


def clip_action() -> dict:
    return {
        "account_id": "liver_manager",
        "slot_id": "lm_1800_clip_media",
        "queue_id": "clip_001",
        "reviewer_id": "reviewer_0001",
        "reviewed_at": "2026-10-11T11:59:00+00:00",
        "decision": "APPROVE",
        "human_checks_confirmed": True,
        "usage_scope": "THREADS_ORGANIC_ONLY",
        "rights_valid_from": "2026-10-01T00:00:00+00:00",
        "rights_expires_at": "2026-12-01T00:00:00+00:00",
        "evidence_ids": {
            "rights_grant": "ev_rights_20261011",
            "publisher_permission": "ev_permission_20261011",
            "source_identity": "ev_source_20261011",
            "media_validation": "ev_media_20261011",
            "caption_quality": "ev_caption_20261011",
            "account_fit": "ev_fit_20261011",
            "asset_provenance": "ev_asset_20261011",
            "clip_lineage": "ev_clip_20261011",
        },
    }


def request_for(plan: dict, *actions: dict) -> dict:
    return {
        "schema_version": "sns_media_review_intake_v1",
        "source_plan_sha256": _sha256(plan),
        "events": list(actions),
    }


def validate(plan: dict, *actions: dict, previous: dict | None = None) -> dict:
    return build_receipts(plan, request_for(plan, *actions), as_of=NOW, previous=previous)


class ReceiptContractTests(unittest.TestCase):
    def test_eligible_clip_approval_is_still_only_an_unverified_draft(self):
        plan = sample_plan()
        receipt = validate(plan, clip_action())
        self.assertEqual(receipt["event_count"], 1)
        self.assertEqual(receipt["new_event_count"], 1)
        self.assertEqual(receipt["status"], "DRAFT_REVIEW_EVENTS_NOT_AUTHORIZED")
        event = receipt["events"][0]
        self.assertEqual(event["review_state"], "APPROVAL_DRAFT_AWAITING_AUTHENTICATED_REVIEW")
        self.assertEqual(event["usage_scope"], "THREADS_ORGANIC_ONLY")
        self.assertEqual(event["rights_expires_at"], "2026-12-01T00:00:00+00:00")
        self.assertEqual(event["source_plan_sha256"], receipt["source_plan_sha256"])
        self.assertEqual(event["previous_event_sha256"], "0" * 64)
        self.assertEqual(event["event_sha256"], receipt["last_event_sha256"])
        for flag in ("publish_authorized", "ready_transitions_performed",
                     "writes_performed", "authenticated_approval", "reviewer_identity_verified"):
            self.assertIs(receipt[flag], False)
        self.assertFalse(event["effective_approval"])
        self.assertFalse(event["reviewer_identity_verified"])

    def test_missing_slot_cannot_be_approved_or_rejected(self):
        plan = sample_plan(eligible_clip=False)
        action = clip_action()
        with self.assertRaisesRegex(ReviewContractError, "candidate_not_in_review_plan"):
            validate(plan, action)
        missing = {
            "account_id": "liver_manager", "slot_id": "lm_1800_clip_media", "queue_id": "",
            "reviewer_id": "reviewer_0001", "reviewed_at": action["reviewed_at"],
            "decision": "REQUEST_EVIDENCE", "reason_code": "evidence_missing",
        }
        receipt = validate(plan, missing)
        self.assertEqual(receipt["events"][0]["review_state"], "EVIDENCE_REQUEST_DRAFT")
        missing["decision"] = "REJECT"
        with self.assertRaisesRegex(ReviewContractError, "missing_candidate_not_rejectable"):
            validate(plan, missing)

    def test_approval_rejected_when_review_plan_has_blockers(self):
        plan = sample_plan()
        item = next(x for x in plan["items"] if x["queue_id"] == "clip_001")
        item["review_state"] = "ACTION_REQUIRED"
        item["priority"] = "P1"
        item["blockers"] = ["rights_human_verification_required"]
        with self.assertRaisesRegex(ReviewContractError, "approval_blocked_by_review_plan_or_replay"):
            validate(plan, clip_action())

    def test_expired_future_or_unscoped_rights_fail_closed(self):
        plan = sample_plan()
        for field, value, code in (
            ("rights_expires_at", "2026-10-10T12:00:00Z", "rights_not_currently_valid"),
            ("rights_valid_from", "2026-10-12T00:00:00Z", "rights_not_currently_valid"),
            ("usage_scope", "PAID_ADVERTISING", "rights_usage_scope_invalid"),
        ):
            action = clip_action()
            action[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ReviewContractError, code):
                validate(plan, action)

    def test_missing_spoofed_or_duplicate_evidence_is_rejected(self):
        plan = sample_plan()
        for mode in ("missing", "fake", "duplicate"):
            action = clip_action()
            if mode == "missing":
                del action["evidence_ids"]["rights_grant"]
            elif mode == "fake":
                action["evidence_ids"]["source_identity"] = "https://example.com/secret"
            else:
                action["evidence_ids"]["source_identity"] = action["evidence_ids"]["rights_grant"]
            with self.subTest(mode=mode), self.assertRaises(ReviewContractError):
                validate(plan, action)

    def test_untrusted_actor_or_metadata_cannot_claim_authentication(self):
        plan = sample_plan()
        for field, value in (
            ("reviewer_identity_verified", True),
            ("publish_authorized", True),
            ("source_url", "https://private.example/token"),
        ):
            action = clip_action()
            action[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ReviewContractError, "record_fields_invalid"):
                validate(plan, action)

    def test_timezone_naive_future_stale_and_missing_explicit_confirmation(self):
        plan = sample_plan()
        for stamp in ("2026-10-11T11:59:00", "2026-10-12T12:00:00+00:00",
                      "2026-09-01T12:00:00+00:00"):
            action = clip_action()
            action["reviewed_at"] = stamp
            with self.subTest(stamp=stamp), self.assertRaises(ReviewContractError):
                validate(plan, action)
        action = clip_action()
        action["human_checks_confirmed"] = False
        with self.assertRaisesRegex(ReviewContractError, "explicit_human_checks_required"):
            validate(plan, action)

    def test_stale_plan_fingerprint_or_plan_safety_violation(self):
        plan = sample_plan()
        intake = request_for(plan, clip_action())
        intake["source_plan_sha256"] = "f" * 64
        with self.assertRaisesRegex(ReviewContractError, "stale_or_wrong_plan_fingerprint"):
            build_receipts(plan, intake, as_of=NOW)
        plan = sample_plan()
        plan["publish_authorized"] = True
        with self.assertRaisesRegex(ReviewContractError, "plan_safety_invariants_invalid"):
            validate(plan, clip_action())

    def test_duplicate_batch_and_out_of_scope_target_are_rejected(self):
        plan = sample_plan()
        action = clip_action()
        with self.assertRaisesRegex(ReviewContractError, "duplicate_action_in_batch"):
            validate(plan, action, action)
        wrong = clip_action()
        wrong["account_id"] = "night_scout"
        with self.assertRaisesRegex(ReviewContractError, "candidate_not_in_review_plan"):
            validate(plan, wrong)

    def test_reject_and_evidence_request_can_log_blocked_candidates(self):
        plan = sample_plan()
        action = clip_action()
        for decision, reason in (("REJECT", "quality_failed"),
                                 ("REQUEST_EVIDENCE", "source_mismatch")):
            item = {
                k: action[k] for k in (
                    "account_id", "slot_id", "queue_id", "reviewer_id", "reviewed_at",
                )
            }
            item.update(decision=decision, reason_code=reason)
            receipt = validate(plan, item)
            event = receipt["events"][0]
            self.assertEqual(event["reason_code"], reason)
            self.assertFalse(event["effective_approval"])
            self.assertFalse(event["publish_authorized"])

    def test_hash_linked_revocation_and_replay_prevention(self):
        plan = sample_plan()
        first = validate(plan, clip_action())
        with self.assertRaisesRegex(ReviewContractError, "approval_blocked_by_review_plan_or_replay"):
            validate(plan, clip_action(), previous=first)
        revoke = {
            k: clip_action()[k] for k in (
                "account_id", "slot_id", "queue_id", "reviewer_id", "reviewed_at",
            )
        }
        revoke.update(decision="REVOKE", reason_code="consent_withdrawn",
                      revokes_event_sha256=first["last_event_sha256"])
        result = validate(plan, revoke, previous=first)
        self.assertEqual(result["event_count"], 2)
        self.assertEqual(result["new_event_count"], 1)
        self.assertEqual(result["events"][1]["previous_event_sha256"], first["last_event_sha256"])
        self.assertEqual(result["events"][1]["review_state"],
                         "REVOCATION_DRAFT_AWAITING_AUTHENTICATED_REVIEW")
        self.assertFalse(result["publish_authorized"])

    def test_history_tampering_or_revocation_without_target_is_rejected(self):
        plan = sample_plan()
        prior = validate(plan, clip_action())
        changed = copy.deepcopy(prior)
        changed["events"][0]["rights_expires_at"] = "2027-10-11T00:00:00+00:00"
        with self.assertRaisesRegex(ReviewContractError, "history_hash_chain_invalid"):
            validate(plan, {"account_id": "liver_manager", "slot_id": "lm_1800_clip_media",
                            "queue_id": "clip_001", "reviewer_id": "reviewer_0001",
                            "reviewed_at": "2026-10-11T11:59:00+00:00",
                            "decision": "REVOKE", "reason_code": "consent_withdrawn",
                            "revokes_event_sha256": prior["last_event_sha256"]}, previous=changed)
        rev = {
            "account_id": "liver_manager", "slot_id": "lm_1800_clip_media",
            "queue_id": "clip_001", "reviewer_id": "reviewer_0001",
            "reviewed_at": "2026-10-11T11:59:00+00:00", "decision": "REVOKE",
            "reason_code": "consent_withdrawn", "revokes_event_sha256": "0" * 64,
        }
        with self.assertRaisesRegex(ReviewContractError, "revocation_target_invalid"):
            validate(plan, rev)

    def test_receipts_do_not_include_unreviewed_raw_media_content(self):
        plan = sample_plan()
        for item in plan["items"]:
            item["source_url"] = "SECRET_SOURCE_URL"
            item["public_post_text"] = "SECRET_POST_TEXT"
            item["private_key"] = "SECRET_PRIVATE_KEY"
        result = json.dumps(validate(plan, clip_action()))
        for token in ("SECRET_SOURCE_URL", "SECRET_POST_TEXT", "SECRET_PRIVATE_KEY"):
            self.assertNotIn(token, result)

    def test_cli_immutable_output_and_no_overwrite(self):
        plan = sample_plan()
        intake = request_for(plan, clip_action())
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            plan_path, intake_path, output_path = (
                base / "plan.json", base / "intake.json", base / "receipts.json"
            )
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            intake_path.write_text(json.dumps(intake), encoding="utf-8")
            cmd = [
                sys.executable, str(ROOT / "scripts/build_media_review_approval_receipts.py"),
                "--plan-json", str(plan_path),
                "--intake-json", str(intake_path),
                "--output-json", str(output_path),
            ]
            first = subprocess.run(cmd, text=True, capture_output=True, check=False)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            saved = output_path.read_bytes()
            self.assertFalse(json.loads(saved)["publish_authorized"])
            second = subprocess.run(cmd, text=True, capture_output=True, check=False)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(output_path.read_bytes(), saved)
            self.assertNotIn(str(output_path), second.stdout)


if __name__ == "__main__":
    unittest.main()
