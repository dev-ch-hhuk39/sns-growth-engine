#!/usr/bin/env python3
"""Offline adversarial review-board plan/sync/apply safety regression.

Fakes emulate persisted Sheets values, lost acknowledgements, and duplicate
identity rows. No credentials, actual Sheets/SNS writes, or production access.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from gspread.utils import a1_to_rowcol

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import apply_publication_review_decisions as decisions  # noqa: E402
import sync_publication_review as sync  # noqa: E402
from review_board_integrity import ReviewBoardBlocked  # noqa: E402
from publication_review_board import review_row  # noqa: E402
from sheets_client import SheetsMutationOutcomeUnknown  # noqa: E402


QUEUE = {
    "queue_id": "q_review_1", "account_id": "night_scout", "platform": "threads",
    "status": "WAITING_REVIEW", "public_post_text": "=literal",
    "validator_status": "PASS", "internal_leak_status": "PASS",
    "media_required": "false", "slot_id": "ns_1600_original",
}
HEADERS = [
    "queue_id", "account_id", "platform", "public_post_text", "review_status",
    "review_decision", "reviewer_note", "decision_applied_at",
    "decision_result", "last_sync_at",
]


def reviewed(*, decision="OK", note="") -> dict:
    return {
        **review_row(QUEUE), "review_decision": decision, "reviewer_note": note,
    }


class FakeSheet:
    def __init__(self, rows, headers):
        self.rows = [dict(r) for r in rows]
        self.headers = list(headers)
        self.append_calls = 0
        self.update_calls = 0
        self.modes = []
        self.fail_after_append = False
        self.fail_after_update = False
        self.drop_updates = False

    def get_all_records(self):
        return [dict(row) for row in self.rows]

    def row_values(self, index):
        assert index == 1
        return list(self.headers)

    def append_rows(self, values, *, value_input_option):
        self.append_calls += 1
        self.modes.append(value_input_option)
        self.rows.extend(dict(zip(self.headers, values_row)) for values_row in values)
        if self.fail_after_append:
            raise TimeoutError("provider may have committed")

    def batch_update(self, ranges, *, value_input_option):
        self.update_calls += 1
        self.modes.append(value_input_option)
        if not self.drop_updates:
            for item in ranges:
                row, col = a1_to_rowcol(item["range"])
                self.rows[row - 2][self.headers[col - 1]] = item["values"][0][0]
        if self.fail_after_update:
            raise TimeoutError("provider may have committed")


class FakeClient:
    def __init__(self, *, queue=None, reviews=None, dry_run=False):
        self.dry_run = dry_run
        self.queue = FakeSheet(
            [dict(r) for r in (queue if queue is not None else [QUEUE])],
            list(QUEUE),
        )
        self.review = FakeSheet(reviews if reviews is not None else [], HEADERS)
        self.queue_updates = []
        self.ensure_calls = 0

    def _ws(self, logical):
        return self.queue if logical == "queue" else self.review

    def _ensure_tab(self, *args, **kwargs):
        self.ensure_calls += 1
        raise AssertionError("implicit schema mutation not permitted")

    def update_queue_item(self, queue_id, **fields):
        # The real SheetsClient independently enforces ID uniqueness,
        # mutable-field allowlist and post-write readback.
        candidates = [row for row in self.queue.rows if row["queue_id"] == queue_id]
        if len(candidates) != 1:
            raise PermissionError("queue_id_not_unique")
        row = candidates[0]
        self.queue_updates.append(queue_id)
        row.update(fields)


class ReviewBoardIsolation(unittest.TestCase):
    def test_preview_never_mutates_schema_or_rows(self):
        fake = FakeClient(reviews=[{
            "queue_id": "q_review_1", "account_id": "night_scout",
            "platform": "threads", "review_decision": "OK",
            "reviewer_note": "do-not-lose", "decision_result": "",
        }], dry_run=True)
        result = sync.sync(fake, apply=False)
        self.assertEqual(result["status"], "PLAN_ONLY")
        self.assertEqual(result["review_rows"][0]["reviewer_note"], "do-not-lose")
        self.assertEqual(result["review_rows"][0]["review_decision"], "OK")
        self.assertEqual(fake.ensure_calls, 0)
        self.assertEqual(fake.review.append_calls, 0)
        self.assertEqual(fake.review.update_calls, 0)
        result = decisions.apply(fake, do_apply=False, allow_media_posts=False)
        self.assertEqual(result["status"], "PLAN_ONLY")
        self.assertFalse(fake.queue_updates)

    def test_sync_append_exact_raw_readback(self):
        fake = FakeClient()
        result = sync.sync(fake, apply=True)
        self.assertEqual(result["status"], "APPLIED")
        self.assertTrue(result["read_after_write"])
        self.assertEqual(fake.review.append_calls, 1)
        self.assertEqual(fake.review.update_calls, 0)
        self.assertEqual(fake.review.modes, ["RAW"])
        self.assertEqual(fake.review.rows[0]["public_post_text"], "=literal")
        self.assertEqual(fake.ensure_calls, 0)

    def test_sync_preserves_editable_review_cells(self):
        fake = FakeClient(reviews=[{
            "queue_id": "q_review_1", "account_id": "night_scout",
            "platform": "threads", "review_decision": "OK",
            "reviewer_note": "operator-text-unchanged",
            "decision_result": "PREEXISTING",
            "decision_applied_at": "2026-10-12T10:00:00+09:00",
            "public_post_text": "old",
        }])
        result = sync.sync(fake, apply=True)
        self.assertTrue(result["read_after_write"])
        saved = fake.review.rows[0]
        self.assertEqual(saved["reviewer_note"], "operator-text-unchanged")
        self.assertEqual(saved["review_decision"], "OK")
        self.assertEqual(saved["decision_result"], "PREEXISTING")
        self.assertEqual(saved["decision_applied_at"], "2026-10-12T10:00:00+09:00")
        self.assertEqual(saved["public_post_text"], "=literal")
        self.assertEqual(fake.review.modes, ["RAW"])

    def test_unknown_ack_after_append_never_retries(self):
        fake = FakeClient()
        fake.review.fail_after_append = True
        with self.assertRaisesRegex(
            SheetsMutationOutcomeUnknown, "manual_reconciliation",
        ):
            sync.sync(fake, apply=True)
        self.assertEqual(fake.review.append_calls, 1)
        self.assertEqual(len(fake.review.rows), 1)

    def test_unknown_ack_after_update_never_retries(self):
        fake = FakeClient(reviews=[{
            "queue_id": "q_review_1", "account_id": "night_scout",
            "platform": "threads", "review_decision": "HOLD",
        }])
        fake.review.fail_after_update = True
        with self.assertRaisesRegex(
            SheetsMutationOutcomeUnknown, "manual_reconciliation",
        ):
            sync.sync(fake, apply=True)
        self.assertEqual(fake.review.update_calls, 1)

    def test_missing_persisted_update_fails_closed(self):
        fake = FakeClient(reviews=[{
            "queue_id": "q_review_1", "account_id": "night_scout",
            "platform": "threads",
        }])
        fake.review.drop_updates = True
        with self.assertRaisesRegex(
            SheetsMutationOutcomeUnknown, "manual_reconciliation",
        ):
            sync.sync(fake, apply=True)
        self.assertEqual(fake.review.update_calls, 1)

    def test_duplicates_in_queue_or_review_block_both_writers_before_mutation(self):
        scenarios = [
            {"queue": [QUEUE, {**QUEUE, "account_id": "liver_manager"}]},
            {"reviews": [
                {"queue_id": "q_review_1", "account_id": "night_scout"},
                {"queue_id": "q_review_1", "account_id": "liver_manager"},
            ]},
        ]
        for kwargs in scenarios:
            for workflow in ("sync", "apply"):
                fake = FakeClient(**kwargs)
                with self.subTest(kwargs=kwargs, workflow=workflow), self.assertRaises(
                    ReviewBoardBlocked,
                ):
                    if workflow == "sync":
                        sync.sync(fake, apply=True)
                    else:
                        decisions.apply(fake, do_apply=True, allow_media_posts=False)
                self.assertFalse(fake.queue_updates)
                self.assertEqual(fake.review.append_calls, 0)
                self.assertEqual(fake.review.update_calls, 0)

    def test_cross_account_review_id_reuse_blocks_without_write(self):
        fake = FakeClient(reviews=[{
            "queue_id": "q_review_1", "account_id": "liver_manager",
            "platform": "threads", "review_decision": "OK",
        }])
        with self.assertRaisesRegex(ReviewBoardBlocked, "REVIEW_ACCOUNT_ID_MISMATCH"):
            decisions.apply(fake, do_apply=True, allow_media_posts=False)
        with self.assertRaises(ReviewBoardBlocked):
            sync.sync(fake, apply=True)
        self.assertFalse(fake.queue_updates)
        self.assertEqual(fake.review.update_calls, 0)

    def test_applied_text_review_requires_both_tabs_readback(self):
        fake = FakeClient(reviews=[reviewed(note="confirmed-by-operator")])
        result = decisions.apply(fake, do_apply=True, allow_media_posts=False)
        self.assertEqual(result["status"], "APPLIED")
        self.assertTrue(result["queue_read_after_write"])
        self.assertTrue(result["review_read_after_write"])
        self.assertEqual(fake.queue.rows[0]["status"], "READY")
        self.assertEqual(fake.queue_updates, ["q_review_1"])
        self.assertEqual(fake.review.rows[0]["decision_result"], "READY")
        self.assertEqual(fake.review.rows[0]["review_status"], "APPROVED")
        self.assertEqual(fake.review.modes, ["RAW"])

    def test_two_tab_partial_ack_never_returns_applied(self):
        fake = FakeClient(reviews=[reviewed()])
        fake.review.fail_after_update = True
        with self.assertRaises(SheetsMutationOutcomeUnknown):
            decisions.apply(fake, do_apply=True, allow_media_posts=False)
        self.assertEqual(fake.queue.rows[0]["status"], "READY")
        self.assertEqual(fake.review.update_calls, 1)
        self.assertEqual(fake.review.rows[0]["decision_result"], "READY")

    def test_readback_failure_is_not_fake_success(self):
        fake = FakeClient(reviews=[reviewed()])
        fake.review.drop_updates = True
        with self.assertRaises(SheetsMutationOutcomeUnknown):
            decisions.apply(fake, do_apply=True, allow_media_posts=False)
        self.assertEqual(fake.review.update_calls, 1)

    def test_sync_preserves_decision_but_marks_changed_content_stale(self):
        reviewed_old = reviewed(note="old-candidate-reviewed")
        fresh = {**QUEUE, "public_post_text": "new text not reviewed"}
        fake = FakeClient(queue=[fresh], reviews=[reviewed_old])
        report = sync.sync(fake, apply=True)
        self.assertEqual(report["status"], "APPLIED")
        self.assertEqual(fake.review.rows[0]["review_decision"], "OK")
        self.assertEqual(fake.review.rows[0]["reviewer_note"], "old-candidate-reviewed")
        self.assertEqual(
            fake.review.rows[0]["review_status"],
            "STALE_REVIEW_RECHECK_REQUIRED",
        )
        apply_result = decisions.apply(
            fake, do_apply=True, allow_media_posts=False,
        )
        self.assertEqual(apply_result["outcomes"], ["BLOCKED_STALE_REVIEW"])
        self.assertEqual(fake.queue.rows[0]["status"], "WAITING_REVIEW")
        self.assertFalse(fake.queue_updates)

    def test_apply_without_sync_detects_material_change_before_mutating(self):
        fake = FakeClient(
            queue=[{**QUEUE, "public_post_text": "replaced after operator OK"}],
            reviews=[reviewed()],
        )
        plan = decisions.apply(fake, do_apply=False, allow_media_posts=False)
        self.assertEqual(plan["outcomes"], ["BLOCKED_STALE_REVIEW"])
        result = decisions.apply(fake, do_apply=True, allow_media_posts=False)
        self.assertEqual(result["outcomes"], ["BLOCKED_STALE_REVIEW"])
        self.assertEqual(fake.queue.rows[0]["status"], "WAITING_REVIEW")
        self.assertEqual(fake.review.rows[0]["decision_result"], "BLOCKED_STALE_REVIEW")

    def test_material_media_identity_drift_blocks_old_decision(self):
        reviewed_old = reviewed()
        fake = FakeClient(
            queue=[{**QUEUE, "media_asset_id": "new_unreviewed_asset"}],
            reviews=[reviewed_old],
        )
        result = decisions.apply(fake, do_apply=False, allow_media_posts=False)
        self.assertEqual(
            result["outcomes"], ["BLOCKED_TRUSTED_MEDIA_REVIEW_REQUIRED"],
        )
        self.assertFalse(fake.queue_updates)
        # Even an otherwise text-only candidate may not inherit an old
        # review if its upstream reference identity changed.
        fake = FakeClient(
            queue=[{**QUEUE, "source_id": "new_unreviewed_source"}],
            reviews=[reviewed()],
        )
        plan = decisions.apply(fake, do_apply=False, allow_media_posts=False)
        self.assertEqual(plan["outcomes"], ["BLOCKED_STALE_REVIEW"])

    def test_clear_then_resync_is_required_before_new_approval(self):
        fake = FakeClient(
            queue=[{**QUEUE, "public_post_text": "new body"}],
            reviews=[reviewed()],
        )
        sync.sync(fake, apply=True)
        # Changing OK to OK cannot renew a stale approval.
        fake.review.rows[0]["review_decision"] = "OK"
        blocked = decisions.apply(fake, do_apply=False, allow_media_posts=False)
        self.assertEqual(blocked["outcomes"], ["BLOCKED_STALE_REVIEW"])
        # Human clears the approval, syncs the new preview, then decides anew.
        fake.review.rows[0]["review_decision"] = ""
        sync.sync(fake, apply=True)
        self.assertEqual(fake.review.rows[0]["review_status"], "PENDING_REVIEW")
        fake.review.rows[0]["review_decision"] = "OK"
        report = decisions.apply(fake, do_apply=True, allow_media_posts=False)
        self.assertEqual(report["outcomes"], ["READY"])
        self.assertEqual(fake.queue.rows[0]["status"], "READY")

    def test_cli_requires_explicit_sheet_target_not_mock_apply_success(self):
        # This rejection must run before get_config/make_client or any I/O.
        for module, confirmation in (
            (sync, "--confirm-review-sync"),
            (decisions, "--confirm-review-decisions"),
        ):
            with self.subTest(module=module.__name__), patch.object(
                sys, "argv", ["review", "--apply", confirmation],
            ), patch.object(
                module, "get_config", side_effect=AssertionError("provider accessed"),
            ), self.assertRaisesRegex(SystemExit, "requires --use-sheets"):
                module.main()

    def test_write_with_dry_run_client_rejected(self):
        fake = FakeClient(dry_run=True)
        with self.assertRaises(ReviewBoardBlocked):
            sync.sync(fake, apply=True)
        with self.assertRaises(ReviewBoardBlocked):
            decisions.apply(fake, do_apply=True, allow_media_posts=False)
        self.assertEqual(fake.ensure_calls, 0)


if __name__ == "__main__":
    unittest.main()
