#!/usr/bin/env python3
"""Post-hoc review never rewrites unchanged applied feedback every schedule."""
from __future__ import annotations
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from publication_review_board import decision_for_row, review_row  # noqa: E402


def queue(status="POSTED"):
    return {
        "queue_id": "test_id", "account_id": "night_scout",
        "platform": "threads", "status": status,
        "public_post_text": "相談を始める前に条件を整理すると安心です。",
        "validator_status": "PASS", "human_review_status": "OK",
        "human_review_note": "確認済み",
        "reviewed_at": "2026-10-24T14:00:00+00:00",
    }


def applied_review(q, decision="OK", note="確認済み"):
    row = review_row(q, {})
    row.update({
        "review_decision": decision, "reviewer_note": note,
        "decision_result": "FEEDBACK_RECORDED",
        "decision_applied_at": "2026-10-24T14:00:00+00:00",
        "review_status": "FEEDBACK_RECORDED",
    })
    return row


class HumanReviewIdempotence(unittest.TestCase):
    def test_applied_feedback_stable(self):
        for status in ("POSTED", "READY"):
            with self.subTest(status=status):
                q = queue(status)
                old = applied_review(q)
                projected = review_row(q, old)
                self.assertEqual(projected["review_status"], "FEEDBACK_RECORDED")
                self.assertEqual(projected["decision_result"], "FEEDBACK_RECORDED")
                self.assertEqual(projected["decision_applied_at"], old["decision_applied_at"])
                self.assertEqual(decision_for_row(projected, q, allow_media_posts=False), ("SKIP", {}))

    def test_legacy_pending_status_recovers_applied_feedback(self):
        q = queue("POSTED")
        old = applied_review(q)
        old["review_status"] = "PENDING_REVIEW"
        projected = review_row(q, old)
        self.assertEqual(projected["review_status"], "FEEDBACK_RECORDED")
        self.assertEqual(
            decision_for_row(projected, q, allow_media_posts=False),
            ("SKIP", {}),
        )

    def test_legacy_pending_changed_text_stays_stale(self):
        q = queue("POSTED")
        old = applied_review(q)
        old["review_status"] = "PENDING_REVIEW"
        q["public_post_text"] = "別の文章へ変更されました。"
        projected = review_row(q, old)
        self.assertEqual(projected["review_status"], "STALE_REVIEW_RECHECK_REQUIRED")

    def test_updated_note_still_processed(self):
        q = queue()
        projected = review_row(q, applied_review(q, note="新しいコメント"))
        outcome, fields = decision_for_row(projected, q, allow_media_posts=False)
        self.assertEqual(outcome, "FEEDBACK_RECORDED")
        self.assertEqual(fields["human_review_note"], "新しいコメント")

    def test_changed_decision_never_retracts_published(self):
        q = queue()
        projected = review_row(q, applied_review(q, decision="NG"))
        outcome, fields = decision_for_row(projected, q, allow_media_posts=False)
        self.assertEqual(outcome, "FEEDBACK_RECORDED")
        self.assertEqual(fields["human_review_status"], "NG")
        self.assertNotIn("status", fields)

    def test_changed_content_blocks_old_feedback(self):
        q = queue()
        old = applied_review(q)
        q["public_post_text"] = "本文変更により改めて審査が必要"
        projected = review_row(q, old)
        self.assertEqual(projected["review_status"], "STALE_REVIEW_RECHECK_REQUIRED")
        self.assertEqual(decision_for_row(projected, q, allow_media_posts=False)[0],
                         "BLOCKED_STALE_REVIEW")

    def test_missing_ack_not_silently_skipped(self):
        q = queue()
        old = applied_review(q)
        old["decision_applied_at"] = ""
        projected = review_row(q, old)
        self.assertEqual(decision_for_row(projected, q, allow_media_posts=False)[0],
                         "FEEDBACK_RECORDED")


if __name__ == "__main__":
    unittest.main()
