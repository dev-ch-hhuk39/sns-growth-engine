#!/usr/bin/env python3
"""Pure offline audit: no writes or secret fields, exact account checks."""
from __future__ import annotations
import unittest
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
from publication_review_board import review_row  # noqa: E402
from sns_local_review_consistency_audit import audit_rows  # noqa: E402


def queue():
    return {
        "queue_id": "test_review", "account_id": "night_scout",
        "platform": "threads", "status": "POSTED",
        "public_post_text": "確認済みのテスト文",
        "human_review_status": "OK", "human_review_note": "確認済み",
        "reviewed_at": "2026-10-25T01:00:00+00:00",
    }


class ReadonlyReviewAuditTests(unittest.TestCase):
    def test_matching_saved_feedback_is_consistent(self):
        q = queue()
        r = review_row(q)
        r.update({
            "review_decision": "OK", "reviewer_note": "確認済み",
            "decision_result": "FEEDBACK_RECORDED",
            "decision_applied_at": "2026-10-25T01:00:00+00:00",
            "review_status": "FEEDBACK_RECORDED",
        })
        x = audit_rows([q], [r])
        self.assertEqual(x["status"], "CONSISTENT")
        self.assertEqual(x["verified_feedback"], 1)
        self.assertEqual(x["social_posts"], 0)
        self.assertEqual(x["sheets_writes"], 0)

    def test_changed_body_needs_reconciliation(self):
        q = queue()
        r = review_row(q)
        q["public_post_text"] = "別の文章に変更した"
        x = audit_rows([q], [r])
        self.assertEqual(x["status"], "REQUIRES_RECONCILIATION")
        self.assertEqual(x["projection_drift"], 1)

    def test_unapplied_feedback_cannot_be_claimed_as_verified(self):
        q = queue()
        r = review_row(q)
        r["review_decision"] = "OK"
        x = audit_rows([q], [r])
        self.assertEqual(x["verified_feedback"], 0)
        self.assertEqual(x["pending_explicit_decisions"], 1)

    def test_missing_review_row_detected(self):
        x = audit_rows([queue()], [])
        self.assertEqual(x["status"], "REQUIRES_RECONCILIATION")
        self.assertEqual(x["missing_review_rows"], 1)


if __name__ == "__main__":
    unittest.main()
