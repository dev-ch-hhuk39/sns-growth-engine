#!/usr/bin/env python3
"""Test exact identity, no fabricated approval and one-row readback."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/"src"), str(ROOT/"scripts")]
import sns_failclosed_unapproved_ready as m  # noqa: E402


class FakeWS:
    def __init__(self, rows):
        self.rows = rows

    def get_all_records(self):
        return [dict(r) for r in self.rows]


class FakeClient:
    def __init__(self, rows, logs=None, posted=None):
        self.queue, self.logs, self.posted = rows, logs or [], posted or []
        self.calls = []

    def _ws(self, name):
        return FakeWS({"queue":self.queue,"logs":self.logs,"posted_results":self.posted}[name])

    def update_queue_item(self, qid, **fields):
        self.calls.append((qid, fields))
        next(r for r in self.queue if r.get("queue_id") == qid).update(fields)

    def get_queue_item(self, qid):
        return next((dict(r) for r in self.queue if r.get("queue_id") == qid), None)


class FailclosedTests(unittest.TestCase):
    def setUp(self):
        self.row = {"queue_id":"q_test_exact", "account_id":"night_scout",
                    "generation_mode":"original_text", "status":"READY",
                    "platform":"threads", "auto_ready_by":"auto_approve_queue.py",
                    "auto_publish":"true"}

    def with_target(self):
        import hashlib
        return patch.object(m,"EXPECTED",hashlib.sha256(self.row["queue_id"].encode()).hexdigest()[:12])

    def test_one_exact_row_and_dry_run(self):
        c = FakeClient([self.row])
        with self.with_target():
            r = m.execute(c,apply=False)
        self.assertEqual(r["status"],"PLAN_ONLY")
        self.assertFalse(c.calls)
        self.assertEqual(self.row["status"],"READY")

    def test_apply_retracts_only_unsupported_ready(self):
        other={"queue_id":"q_other","account_id":"liver_manager","status":"READY"}
        c=FakeClient([self.row,other])
        with self.with_target(), patch.dict("os.environ",{"BUFFERED_POSTING_ENABLED":"false"}):
            r=m.execute(c,apply=True)
        self.assertEqual(r["status"],"REVIEW_REQUIRED_SAFELY")
        self.assertEqual(self.row["status"],"WAITING_REVIEW")
        self.assertEqual(self.row["auto_publish"],"false")
        self.assertEqual(other["status"],"READY")
        self.assertEqual(len(c.calls),1)
        self.assertEqual(r["posts"],0)
        self.assertEqual(r["approval_logs_created"],0)

    def test_existing_approval_log_blocks(self):
        log={"operation":"queue_approved","details":"queue_id=q_test_exact"}
        with self.with_target(), self.assertRaises(ValueError):
            m.plan([self.row],[log],[])

    def test_posted_or_duplicate_blocks(self):
        with self.with_target():
            with self.assertRaises(ValueError):
                m.plan([self.row],[ ],[{"queue_id":"q_test_exact"}])
            with self.assertRaises(ValueError):
                m.plan([self.row,self.row],[],[])

    def test_media_or_other_owner_blocks(self):
        with self.with_target():
            for patch_data in ({"media_required":"true"},{"media_asset_id":"media_1"},
                               {"human_approved":"true"},{"auto_ready_by":"different"}):
                row={**self.row,**patch_data}
                with self.subTest(patch_data=patch_data),self.assertRaises(ValueError):
                    m.plan([row],[],[])

    def test_explicit_post_off_required(self):
        c=FakeClient([self.row])
        with self.with_target(),patch.dict("os.environ",{"BUFFERED_POSTING_ENABLED":"true"}),self.assertRaises(ValueError):
            m.execute(c,apply=True)
        self.assertFalse(c.calls)


if __name__=="__main__":
    unittest.main()
