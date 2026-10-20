#!/usr/bin/env python3
"""Local-only regression: reconcile historical unreviewed mirror duplicates safely."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/"src"),str(ROOT/"scripts")]
import sync_publication_review as sync
import apply_publication_review_decisions as decisions
from review_board_integrity import index_review_rows,ReviewBoardBlocked
from publication_review_board import review_row
from test_publication_review_write_safety import FakeClient,QUEUE,reviewed

OLD="2026-08-11T09:16:24+00:00"
NEW="2026-10-05T05:49:13+00:00"
def pair():
    row=review_row(QUEUE)
    old={**row,"last_sync_at":OLD,"updated_at":OLD,"created_at":OLD,
         "review_decision":"","reviewer_note":"","decision_result":"",
         "decision_applied_at":"","review_status":"PENDING_REVIEW"}
    new={**row,"last_sync_at":NEW,"updated_at":NEW,"created_at":NEW,
         "review_decision":"","reviewer_note":"","decision_result":"",
         "decision_applied_at":"","review_status":"PENDING_REVIEW"}
    return old,new

class LegacyReviewMirrors(unittest.TestCase):
    def test_older_unreviewed_mirror_coalesces_without_mutation(self):
        old,new=pair()
        new["public_post_text"]="updated copy"
        result=index_review_rows([old,new],source="REVIEW")
        self.assertEqual(result[QUEUE["queue_id"]]["public_post_text"],"updated copy")
        self.assertEqual(old["public_post_text"],QUEUE["public_post_text"])
        with self.assertRaises(ReviewBoardBlocked):
            index_review_rows([old,new],source="QUEUE")

    def test_full_58_cohort_only_collapses_logically(self):
        sample=[]
        for i in range(58):
            old,new=pair()
            old["queue_id"]=new["queue_id"]=f"legacy_{i}"
            old["review_id"]=new["review_id"]=f"review_legacy_{i}"
            sample.extend([old,new])
        self.assertEqual(len(index_review_rows(sample,source="REVIEW")),58)
        self.assertEqual(len(sample),116)

    def test_old_reviewer_input_and_identity_ambiguity_always_block(self):
        patches=(
            {"review_decision":"OK"},{"reviewer_note":"do-not-lose"},
            {"decision_applied_at":"yesterday"},{"decision_result":"READY"},
            {"account_id":"liver_manager"},{"review_id":"other"},
            {"platform":"x"},{"post_type":"media"},{"review_status":"APPROVED"},
            {"last_sync_at":NEW},{"last_sync_at":"bad"},
            {"last_sync_at":"2027-01-01T00:00:00Z"}
        )
        for change in patches:
            old,new=pair();old.update(change)
            with self.subTest(change=change),self.assertRaisesRegex(ReviewBoardBlocked,"REVIEW_QUEUE_ID_DUPLICATE"):
                index_review_rows([old,new],source="REVIEW")
        old,new=pair()
        with self.assertRaises(ReviewBoardBlocked):
            index_review_rows([old,new,dict(new)],source="REVIEW")

    def test_newer_identity_or_timestamp_mismatch_blocks(self):
        for change in ({"last_sync_at":"bad"},{"last_sync_at":OLD},
                       {"account_id":"beauty_account"},{"review_id":"other"}):
            old,new=pair();new.update(change)
            with self.subTest(change=change),self.assertRaises(ReviewBoardBlocked):
                index_review_rows([old,new],source="REVIEW")

    def test_sync_uses_latest_and_does_not_touch_old(self):
        old,new=pair();new["public_post_text"]="old unreviewed text"
        client=FakeClient(reviews=[old,new])
        result=sync.sync(client,apply=True)
        self.assertEqual(result["status"],"APPLIED")
        self.assertTrue(result["read_after_write"])
        self.assertEqual(result["legacy_unreviewed_duplicate_rows_preserved"],1)
        self.assertEqual(client.review.rows[0],old)
        self.assertEqual(client.review.rows[1]["public_post_text"],QUEUE["public_post_text"])
        self.assertFalse(client.queue_updates)

    def test_unchanged_review_no_timestamp_rewrites(self):
        row=review_row(QUEUE)
        row.update(last_sync_at=OLD,updated_at=OLD)
        client=FakeClient(reviews=[row])
        result=sync.sync(client,apply=True)
        self.assertEqual(result["status"],"APPLIED")
        self.assertEqual(result["updated_count"],0)
        self.assertEqual(client.review.update_calls,0)

    def test_latest_human_approval_can_be_applied_not_old_one(self):
        old,new=pair()
        new={**new,**reviewed(decision="OK",note="explicit decision")}
        new["last_sync_at"]=NEW
        client=FakeClient(reviews=[old,new])
        report=decisions.apply(client,do_apply=True,allow_media_posts=False)
        self.assertEqual(report["outcomes"],["READY"])
        self.assertEqual(client.review.rows[0],old)
        self.assertEqual(client.review.rows[1]["decision_result"],"READY")
        self.assertEqual(client.queue.rows[0]["status"],"READY")

    def test_old_vote_blocks_both_writers_before_mutations(self):
        old,new=pair();old["review_decision"]="OK"
        for which in ("sync","apply"):
            client=FakeClient(reviews=[old,new])
            with self.subTest(which=which),self.assertRaises(ReviewBoardBlocked):
                if which=="sync":sync.sync(client,apply=True)
                else:decisions.apply(client,do_apply=True,allow_media_posts=False)
            self.assertEqual(client.review.update_calls,0)
            self.assertEqual(client.review.append_calls,0)
            self.assertFalse(client.queue_updates)

if __name__=="__main__":unittest.main()
