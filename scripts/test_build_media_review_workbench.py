#!/usr/bin/env python3
"""Offline regression for the Phase 5B-3 media review-only workbench."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_media_review_approval_receipts import ReviewContractError  # noqa: E402
from build_media_review_workbench import (  # noqa: E402
    build_workbench, render_html,
)
from test_build_media_review_approval_receipts import (  # noqa: E402
    NOW, clip_action, sample_plan, validate,
)


def queue_snapshot() -> dict:
    return {
        "schema_version": "sns_media_queue_snapshot_v1",
        "read_only": True,
        "captured_at": NOW.isoformat(),
        "rows": [{
            "account_id": "liver_manager",
            "slot_id": "lm_1800_clip_media",
            "queue_id": "clip_001",
            "media_asset_id": "media_asset_001",
            "status": "READY",
            "rights_status": "APPROVED",
            "permission_status": "APPROVED",
            "rights_review_required": False,
            "validator_status": "PASS",
            "internal_leak_status": "PASS",
            "account_fit_status": "PASS",
            "alignment_status": "PASS",
            "hybrid_ai_status": "PASS",
            "public_post_text": "PRIVATE_POST_BODY",
            "source_url": "https://secret.example/private_source",
        }],
    }


def evidence_snapshot(action: dict | None = None) -> dict:
    action = action or clip_action()
    return {
        "schema_version": "sns_media_evidence_snapshot_v1",
        "read_only": True,
        "captured_at": NOW.isoformat(),
        "records": [
            {
                "evidence_id": evidence_id,
                "account_id": "liver_manager",
                "slot_id": "lm_1800_clip_media",
                "queue_id": "clip_001",
                "media_asset_id": "media_asset_001",
                "kind": kind,
                "verification_status": "VERIFIED",
                "usage_scope": "THREADS_ORGANIC_ONLY",
                "rights_valid_from": "2026-10-01T00:00:00+00:00",
                "rights_expires_at": "2026-12-01T00:00:00+00:00",
                "revoked": False,
                "raw_evidence_text": "SENSITIVE_EVIDENCE",
            }
            for kind, evidence_id in action["evidence_ids"].items()
        ],
    }


class MediaWorkbenchTests(unittest.TestCase):
    def test_no_evidence_or_queue_blocks_every_candidate(self):
        board = build_workbench(sample_plan(), as_of=NOW)
        self.assertEqual(board["schema_version"], "sns_media_review_workbench_v1")
        self.assertEqual(board["item_count"], 4)
        self.assertFalse(board["publish_authorized"])
        self.assertFalse(board["authenticated_approval"])
        self.assertFalse(board["writes_performed"])
        self.assertTrue(all("queue_snapshot_missing" in item["action_required"]
                            for item in board["items"]))
        self.assertTrue(all("authenticated_reviewer_missing" in item["action_required"]
                            for item in board["items"]))

    def test_matching_queue_and_evidence_remain_draft_only(self):
        plan = sample_plan()
        receipts = validate(plan, clip_action())
        queue = queue_snapshot()
        evidence = evidence_snapshot()
        saved = json.dumps((plan, receipts, queue, evidence), sort_keys=True)
        board = build_workbench(plan, receipts=receipts, queue_snapshot=queue,
                                evidence_snapshot=evidence, as_of=NOW)
        clip = next(item for item in board["items"] if item["queue_id"] == "clip_001")
        self.assertEqual(clip["review_state"], "AUTHENTICATION_REQUIRED")
        self.assertEqual(clip["action_required"], ["authenticated_reviewer_missing"])
        self.assertFalse(clip["authenticated_approval"])
        self.assertFalse(clip["publish_authorized"])
        self.assertFalse(clip["canonical_ready_verified"])
        self.assertTrue(board["queue_snapshot_current"])
        self.assertTrue(board["evidence_snapshot_current"])
        self.assertEqual(saved, json.dumps((plan, receipts, queue, evidence), sort_keys=True))

    def test_expired_or_revoked_evidence_cannot_be_promoted(self):
        plan = sample_plan()
        receipts = validate(plan, clip_action())
        for change, reason in (
            ({"rights_expires_at": "2026-10-10T00:00:00+00:00"}, "evidence_not_verified"),
            ({"revoked": True}, "evidence_not_verified"),
            ({"verification_status": "PENDING"}, "evidence_not_verified"),
            ({"usage_scope": "PAID_ADVERTISING"}, "evidence_record_mismatch"),
            ({"media_asset_id": "another_asset"}, "evidence_record_mismatch"),
            ({"account_id": "night_scout"}, "evidence_record_mismatch"),
        ):
            evidence = evidence_snapshot()
            evidence["records"][0].update(change)
            with self.subTest(change=change):
                board = build_workbench(plan, receipts=receipts,
                                        queue_snapshot=queue_snapshot(),
                                        evidence_snapshot=evidence, as_of=NOW)
                clip = next(item for item in board["items"] if item["queue_id"] == "clip_001")
                self.assertIn(reason, clip["action_required"])
                self.assertFalse(clip["publish_authorized"])

    def test_stale_or_future_dated_snapshot_is_not_current(self):
        plan = sample_plan()
        receipt = validate(plan, clip_action())
        for delta in (timedelta(hours=-1), timedelta(minutes=5)):
            q = queue_snapshot()
            q["captured_at"] = (NOW + delta).isoformat()
            board = build_workbench(plan, receipts=receipt,
                                    queue_snapshot=q,
                                    evidence_snapshot=evidence_snapshot(), as_of=NOW)
            clip = next(item for item in board["items"] if item["queue_id"] == "clip_001")
            self.assertIn("queue_snapshot_stale", clip["action_required"])
            self.assertFalse(board["queue_snapshot_current"])

    def test_mismatched_account_and_quality_hold_queue(self):
        plan = sample_plan()
        receipts = validate(plan, clip_action())
        row = queue_snapshot()
        row["rows"][0]["account_id"] = "night_scout"
        row["rows"][0]["rights_review_required"] = True
        row["rows"][0]["validator_status"] = "FAILED"
        board = build_workbench(plan, receipts=receipts, queue_snapshot=row,
                                evidence_snapshot=evidence_snapshot(), as_of=NOW)
        clip = next(item for item in board["items"] if item["queue_id"] == "clip_001")
        for blocker in ("queue_account_or_slot_mismatch", "queue_quality_gate_not_passed",
                        "queue_rights_review_pending"):
            self.assertIn(blocker, clip["action_required"])

    def test_duplicate_queue_or_proof_records_fail_closed(self):
        plan = sample_plan()
        q = queue_snapshot()
        q["rows"].append(copy.deepcopy(q["rows"][0]))
        with self.assertRaisesRegex(ReviewContractError, "snapshot_queue_duplicate"):
            build_workbench(plan, queue_snapshot=q, as_of=NOW)
        ev = evidence_snapshot()
        ev["records"].append(copy.deepcopy(ev["records"][0]))
        with self.assertRaisesRegex(ReviewContractError, "snapshot_evidence_duplicate"):
            build_workbench(plan, evidence_snapshot=ev, as_of=NOW)

    def test_wrong_snapshot_schema_or_write_mode_fails_closed(self):
        for key in ("schema_version", "read_only"):
            q = queue_snapshot()
            q[key] = "WRONG" if key == "schema_version" else False
            with self.subTest(key=key), self.assertRaisesRegex(
                ReviewContractError, "snapshot_not_read_only"
            ):
                build_workbench(sample_plan(), queue_snapshot=q, as_of=NOW)

    def test_previous_receipts_chain_is_required(self):
        plan = sample_plan()
        receipts = validate(plan, clip_action())
        receipts["events"][0]["rights_expires_at"] = "2028-10-11T00:00:00+00:00"
        with self.assertRaisesRegex(ReviewContractError, "history_hash_chain_invalid"):
            build_workbench(plan, receipts=receipts, as_of=NOW)

    def test_explicit_account_scope_prevents_other_account_cards(self):
        board = build_workbench(sample_plan(), account_id="night_scout", as_of=NOW)
        self.assertEqual(board["item_count"], 2)
        self.assertTrue(all(x["account_id"] == "night_scout" for x in board["items"]))
        with self.assertRaisesRegex(ReviewContractError, "workbench_account_scope_invalid"):
            build_workbench(sample_plan(), account_id="beauty_account", as_of=NOW)

    def test_html_is_escaped_and_has_no_network_or_approval_form(self):
        plan = sample_plan()
        clip = next(x for x in plan["items"] if x["queue_id"] == "clip_001")
        clip["queue_id"] = "clip_001<script>alert(1)</script>"
        # Invalid identifiers fail closed before output.
        with self.assertRaisesRegex(ReviewContractError, "plan_queue_id_invalid"):
            build_workbench(plan, as_of=NOW)
        plan = sample_plan()
        plan["items"][0]["public_post_text"] = "SECRET_POST_TEXT"
        plan["items"][0]["source_url"] = "https://secret.example"
        board = build_workbench(plan, as_of=NOW)
        page = render_html(board)
        for payload in ("SECRET_POST_TEXT", "secret.example", "<iframe",
                        "<form", "<img", "fetch(", "document.cookie"):
            self.assertNotIn(payload, page)
        self.assertIn("Content-Security-Policy", page)
        self.assertIn("connect-src 'none'", page)
        self.assertIn("認証済み担当者", page)
        self.assertIn('id="account"', page)

    def test_local_html_output_is_private_and_never_overwritten(self):
        plan = sample_plan()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            input_file = root / "plan.json"
            output = root / "review.html"
            input_file.write_text(json.dumps(plan), encoding="utf-8")
            cmd = [sys.executable, str(ROOT / "scripts/build_media_review_workbench.py"),
                   "--plan-json", str(input_file), "--output-html", str(output)]
            result = subprocess.run(cmd, check=False, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(os.stat(output).st_mode & 0o777, 0o600)
            old = output.read_bytes()
            rerun = subprocess.run(cmd, check=False, capture_output=True, text=True)
            self.assertEqual(rerun.returncode, 2)
            self.assertEqual(output.read_bytes(), old)
            self.assertNotIn(str(output), rerun.stdout)


if __name__ == "__main__":
    unittest.main()
