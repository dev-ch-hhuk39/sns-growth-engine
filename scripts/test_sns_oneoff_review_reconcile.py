#!/usr/bin/env python3
"""Pure offline restrictions for one-time publication-review recovery."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]
import sns_oneoff_review_reconcile as fix  # noqa: E402


def queue(qid: str, status: str = "WAITING_REVIEW") -> dict:
    return {
        "queue_id": qid, "account_id": "night_scout", "platform": "threads",
        "status": status, "public_post_text": "投稿本文。", "human_review_status": "",
    }


class OneOffReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = fix.patched_review_module()

    def test_missing_rows_limited(self):
        result = fix.validated_plan([queue("q1")], [], self.helper)
        self.assertEqual(result["missing"], 1)
        self.assertEqual(result["drift_rows"], 0)
        self.assertEqual(result["posts"], 0)
        self.assertEqual(result["reviewer_decision_writes"], 0)

    def test_duplicate_identity_fails_closed(self):
        with self.assertRaises(Exception):
            fix.validated_plan([queue("q1"), queue("q1")], [], self.helper)

    def test_reviewer_decision_never_implicitly_applied(self):
        q = queue("q1", "READY")
        review = self.helper.review_row(q)
        review["review_decision"] = "OK"
        with self.assertRaises(ValueError):
            fix.validated_plan([q], [review], self.helper)

    def test_legacy_applied_feedback_permitted_only_if_queue_matches(self):
        q = queue("q1", "POSTED")
        q.update({"human_review_status": "OK", "human_review_note": "完了",
                  "reviewed_at": "2026-10-25T09:00:00Z"})
        existing = self.helper.review_row(q)
        existing.update({"review_decision": "OK", "reviewer_note": "完了",
                         "decision_result": "FEEDBACK_RECORDED",
                         "decision_applied_at": "2026-10-25T09:00:00Z",
                         "review_status": "PENDING_REVIEW"})
        with self.assertRaises(ValueError) as err:
            fix.validated_plan([q], [existing], self.helper)
        self.assertEqual(str(err.exception), "MISSING_REVIEW_BATCH_NOT_WITHIN_BOUNDS")
        # The one-off repair intentionally requires missing rows; no-op
        # executions cannot silently repeat the earlier unknown write.
        expected = self.helper.review_row(q, existing)
        self.assertEqual(expected["review_status"], "FEEDBACK_RECORDED")

    def test_material_change_after_applied_feedback_blocks(self):
        q = queue("q1", "POSTED")
        q.update({"human_review_status": "OK", "human_review_note": "完了",
                  "reviewed_at": "2026-10-25T09:00:00Z"})
        existing = self.helper.review_row(q)
        existing.update({"review_decision": "OK", "reviewer_note": "完了",
                         "decision_result": "FEEDBACK_RECORDED",
                         "decision_applied_at": "2026-10-25T09:00:00Z",
                         "review_status": "FEEDBACK_RECORDED"})
        q["public_post_text"] = "変更された本文"
        with self.assertRaises(ValueError) as e:
            fix.validated_plan([q, queue("new1")], [existing], self.helper)
        self.assertEqual(str(e.exception), "APPLIED_FEEDBACK_MATERIAL_CHANGE")

    def test_missing_over_hard_limit_fails(self):
        with self.assertRaises(ValueError):
            fix.validated_plan([queue(str(i)) for i in range(fix.MAX_NEW + 1)], [], self.helper)


if __name__ == "__main__":
    unittest.main()
