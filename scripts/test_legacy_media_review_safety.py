#!/usr/bin/env python3
"""Phase 5B-4B/4C: legacy review strict-mode + offline audit regression."""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from audit_legacy_media_review import LegacyAuditBlocked, build_legacy_media_audit  # noqa: E402
from media_review_legacy_guard import (  # noqa: E402
    is_protected_media_candidate, requires_strict_review_block,
)
from publication_review_board import decision_for_row  # noqa: E402
from apply_publication_review_decisions import build_decisions  # noqa: E402
from scripts.approve_queue import cmd_approve  # noqa: E402


def media_queue(**overrides) -> dict:
    row = {
        "account_id": "night_scout",
        "slot_id": "ns_1800_direct_media",
        "queue_id": "media_001",
        "platform": "threads",
        "status": "WAITING_REVIEW",
        "public_post_text": "素材つき投稿のテストです。",
        "validator_status": "PASS",
        "internal_leak_status": "PASS",
        "media_required": "true",
        "media_asset_id": "asset_001",
        "media_url": "https://private.example/media.png",
        "media_type": "IMAGE",
        "media_status": "UPLOADED",
        "rights_status": "APPROVED",
        "permission_status": "APPROVED",
    }
    row.update(overrides)
    return row


def sample_snapshot() -> dict:
    return {
        "schema_version": "sns_media_queue_snapshot_v1",
        "read_only": True,
        "captured_at": "2026-10-11T00:00:00Z",
        "rows": [
            media_queue(status="WAITING_REVIEW", queue_id="media_wait"),
            media_queue(status="READY", queue_id="media_ready",
                        public_post_text="PRIVATE_POST_TEXT",
                        source_url="https://private.example/private"),
            media_queue(status="POSTED", queue_id="media_posted"),
            {
                "account_id": "night_scout", "queue_id": "text_001",
                "slot_id": "text_0900", "status": "READY",
                "public_post_text": "通常テキストです。",
            },
            media_queue(account_id="beauty_account", queue_id="beauty_media"),
        ],
    }


class FakeSheets:
    def __init__(self, queue):
        self.queue = dict(queue)
        self.updated = []
        self.logs = []

    def get_queue_item(self, queue_id):
        return dict(self.queue) if queue_id == self.queue["queue_id"] else None

    def update_queue_item(self, queue_id, **kwargs):
        self.updated.append((queue_id, kwargs))

    def log(self, **kwargs):
        self.logs.append(kwargs)


class LegacyMediaReviewSafetyTests(unittest.TestCase):
    def test_protected_slot_detected_without_trusting_media_required_flag(self):
        row = media_queue(media_required="false", media_asset_id="", media_url="",
                          media_type="", media_status="", generation_mode="")
        self.assertTrue(is_protected_media_candidate(row))
        self.assertTrue(requires_strict_review_block(
            row, desired_status="READY", strict_trusted_media_review=True))
        self.assertFalse(requires_strict_review_block(
            row, desired_status="REJECTED", strict_trusted_media_review=True))
        self.assertFalse(requires_strict_review_block(
            row, desired_status="READY", strict_trusted_media_review=False))

    def test_missing_slot_id_with_media_markers_still_protected(self):
        for change in (
            {"slot_id": "", "media_required": "yes"},
            {"slot_id": "", "media_required": "false", "clip_candidate_id": "clip_7"},
            {"slot_id": "", "media_required": "false", "media_type": "VIDEO"},
            {"slot_id": "", "media_required": "false", "media_url": "https://sample.local/a"},
            {"slot_id": "", "media_required": "false", "generation_mode": "approved_source_clip"},
        ):
            row = media_queue(media_asset_id="", media_url="", media_type="",
                              generation_mode="")
            row.update(change)
            with self.subTest(change=change):
                self.assertTrue(is_protected_media_candidate(row))

    def test_text_and_non_target_accounts_unchanged(self):
        plain = {
            "account_id": "night_scout", "slot_id": "ns_0900_text",
            "status": "WAITING_REVIEW", "validator_status": "PASS",
            "internal_leak_status": "PASS", "platform": "threads",
            "public_post_text": "テキストの例",
        }
        self.assertFalse(is_protected_media_candidate(plain))
        self.assertFalse(is_protected_media_candidate(media_queue(account_id="beauty_account")))
        self.assertEqual(
            decision_for_row({"review_decision": "OK"}, plain,
                             allow_media_posts=False,
                             strict_trusted_media_review=True)[0], "READY",
        )

    def test_sheets_strict_mode_blocks_media_without_modifying_queue(self):
        review = {"queue_id": "media_001", "review_decision": "OK",
                  "reviewer_note": "確認済みという自己申告"}
        queue = media_queue()
        status, changed = decision_for_row(review, queue, allow_media_posts=False,
                                           strict_trusted_media_review=True)
        self.assertEqual(status, "BLOCKED_TRUSTED_MEDIA_REVIEW_REQUIRED")
        self.assertEqual(changed, {})
        plan = build_decisions([review], [queue], allow_media_posts=False,
                               strict_trusted_media_review=True)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0][2], "BLOCKED_TRUSTED_MEDIA_REVIEW_REQUIRED")
        self.assertEqual(plan[0][3], {})

    def test_legacy_default_behavior_preserved_for_compatibility(self):
        review = {"queue_id": "media_001", "review_decision": "OK"}
        queue = media_queue()
        self.assertEqual(
            decision_for_row(review, queue, allow_media_posts=False)[0], "READY")
        self.assertEqual(
            build_decisions([review], [queue], allow_media_posts=False)[0][2], "READY")

    def test_strict_mode_does_not_block_rejections_holds_or_posthoc_feedback(self):
        queue = media_queue()
        self.assertEqual(
            decision_for_row({"review_decision": "NG"}, queue,
                             allow_media_posts=False,
                             strict_trusted_media_review=True)[0], "REJECTED")
        self.assertEqual(
            decision_for_row({"review_decision": "HOLD"}, queue,
                             allow_media_posts=False,
                             strict_trusted_media_review=True)[0], "HOLD")
        ready = media_queue(status="READY")
        outcome, changes = decision_for_row(
            {"review_decision": "OK"}, ready, allow_media_posts=False,
            strict_trusted_media_review=True,
        )
        self.assertEqual(outcome, "FEEDBACK_RECORDED")
        self.assertNotIn("status", changes)

    def test_approval_cli_strict_mode_refuses_before_writes(self):
        fake = FakeSheets(media_queue())
        rc = cmd_approve(fake, "media_001", "READY", "手動承認",
                         False, strict_trusted_media_review=True)
        self.assertEqual(rc, 1)
        self.assertEqual(fake.updated, [])
        self.assertEqual(fake.logs, [])

    def test_audit_flags_legacy_queue_states_without_exposing_content(self):
        snapshot = sample_snapshot()
        before = copy.deepcopy(snapshot)
        result = build_legacy_media_audit(snapshot)
        self.assertEqual(result["source_row_count"], 5)
        self.assertEqual(result["protected_media_rows"], 3)
        self.assertEqual(result["other_rows"], 2)
        self.assertEqual(result["counts"], {"WAITING_REVIEW": 1, "READY": 1, "POSTED": 1})
        self.assertEqual(result["items"][0]["observed_status"], "READY")
        self.assertFalse(result["authenticated_approval_verified"])
        self.assertFalse(result["publish_authorized"])
        self.assertFalse(result["writes_performed"])
        self.assertEqual(snapshot, before)
        rendered = json.dumps(result)
        for text in ("PRIVATE_POST_TEXT", "private.example", "素材つき投稿", "permission_status"):
            self.assertNotIn(text, rendered)

    def test_missing_schema_or_read_only_flag_or_duplicate_fail_closed(self):
        for update in (
            {"read_only": False},
            {"schema_version": "untrusted"},
            {"rows": "malformed"},
            {"captured_at": None},
            {"captured_at": "PRIVATE_ACCESS_TOKEN"},
            {"captured_at": "2026-10-11T00:00:00"},
        ):
            source = sample_snapshot()
            source.update(update)
            with self.subTest(update=update), self.assertRaises(LegacyAuditBlocked):
                build_legacy_media_audit(source)
        source = sample_snapshot()
        source["rows"].append(copy.deepcopy(source["rows"][0]))
        with self.assertRaisesRegex(LegacyAuditBlocked, "duplicate_queue_identity"):
            build_legacy_media_audit(source)

    def test_untrusted_sensitive_queue_ids_not_exported(self):
        source = sample_snapshot()
        source["rows"][0]["queue_id"] = "unsafe\nSECRET_AUTHORIZATION"
        with self.assertRaisesRegex(LegacyAuditBlocked, "queue_identity_invalid"):
            build_legacy_media_audit(source)

    def test_private_no_overwrite_cli_output(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            src = base / "queue.json"
            out = base / "report.json"
            src.write_text(json.dumps(sample_snapshot()), encoding="utf-8")
            cmd = [
                sys.executable, str(ROOT / "scripts/audit_legacy_media_review.py"),
                "--queue-snapshot-json", str(src),
                "--output-json", str(out),
            ]
            first = subprocess.run(cmd, check=False, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            original = out.read_bytes()
            self.assertEqual(os.stat(out).st_mode & 0o777, 0o600)
            second = subprocess.run(cmd, check=False, capture_output=True, text=True)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(out.read_bytes(), original)
            self.assertNotIn(str(src), second.stdout)

    def test_source_code_has_explicit_strict_switches_but_default_unchanged(self):
        board = (ROOT / "scripts/publication_review_board.py").read_text()
        cli = (ROOT / "scripts/approve_queue.py").read_text()
        batch = (ROOT / "scripts/apply_publication_review_decisions.py").read_text()
        for source in (board, cli, batch):
            self.assertIn("strict_trusted_media_review", source)
        self.assertIn("--require-trusted-media-review", cli)
        self.assertIn("--require-trusted-media-review", batch)
        self.assertIn("strict_trusted_media_review: bool = False", board)
        self.assertIn("strict_trusted_media_review: bool = False", batch)


if __name__ == "__main__":
    unittest.main()
