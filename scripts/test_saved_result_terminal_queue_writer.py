#!/usr/bin/env python3
"""Regression for exact verified-repair bypass of ordinary final-state guard.

This is offline and intentionally has no network, provider credentials, posting,
or external Sheets writes.
"""
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from scripts import recover_orphan_threads_post as repair  # noqa: E402


QUEUE_ID = "queue_exact_save_failure_01"
RESULT_ID = "result_already_written_01"
TEXT = "検証用に既に投稿済みとする文章"


def row():
    return {
        "queue_id": QUEUE_ID,
        "account_id": "liver_manager",
        "platform": "threads",
        "draft_id": "draft-1",
        "public_post_text": TEXT,
        "status": "POSTED_SAVE_FAILED",
        "error": "lost acknowledgement",
        "result_id": "",
    }


class FakeWorksheet:
    def __init__(self):
        self.headers = list(row())
        self.rows = [row()]
        self.writes = []
        self.raise_during_write = False
        self.duplicate_id = False
        self.forbid_commit = False

    def row_values(self, rnum):
        if rnum == 1:
            return list(self.headers)
        if rnum == 2:
            return [self.rows[0].get(k, "") for k in self.headers]
        return []

    def findall(self, query, *, in_column):
        assert query == QUEUE_ID
        assert in_column == self.headers.index("queue_id") + 1
        matched = [SimpleNamespace(row=2, value=QUEUE_ID)]
        if self.duplicate_id:
            matched.append(SimpleNamespace(row=3, value=QUEUE_ID))
        return matched


class FakeClient:
    def __init__(self):
        self.dry_run = False
        self.ws = FakeWorksheet()
        self.reads = []

    def _ws(self, logical):
        assert logical == "queue"
        return self.ws

    def _call_with_rate_limit_retry(self, label, callback):
        self.reads.append(label)
        return callback()

    def _batch_update_fields(self, ws, headers, rownum, fields, *, label):
        assert ws is self.ws
        assert headers == self.ws.headers and rownum == 2
        assert label.startswith("queue:")
        assert set(fields) == {"status", "error", "result_id"}
        self.ws.writes.append(copy.deepcopy(fields))
        if self.ws.raise_during_write:
            raise RuntimeError("ambiguous remote write (do not retry)")
        if not self.ws.forbid_commit:
            self.ws.rows[0].update(fields)


def write(client, *, expected_draft_id="draft-1", result_id=RESULT_ID):
    return repair._write_verified_saved_result_queue_only(
        client, queue_id=QUEUE_ID, account_id="liver_manager",
        expected_text=TEXT, expected_draft_id=expected_draft_id,
        result_id=result_id,
    )


class SavedResultQueueWriterTests(unittest.TestCase):
    def test_exact_persisted_post_makes_one_queue_only_update(self):
        c = FakeClient()
        self.assertTrue(write(c))
        self.assertEqual(c.ws.rows[0]["status"], "POSTED")
        self.assertEqual(c.ws.rows[0]["result_id"], RESULT_ID)
        self.assertEqual(c.ws.rows[0]["error"], "")
        self.assertEqual(c.ws.rows[0]["queue_id"], QUEUE_ID)
        self.assertEqual(c.ws.rows[0]["draft_id"], "draft-1")
        self.assertEqual(len(c.ws.writes), 1)
        self.assertIn("row_values:queue:saved_result_repair:readback", c.reads)

    def test_duplicate_queue_id_fails_before_write(self):
        c = FakeClient()
        c.ws.duplicate_id = True
        with self.assertRaisesRegex(PermissionError, "identity_ambiguous"):
            write(c)
        self.assertFalse(c.ws.writes)

    def test_nonfailed_status_never_reopened(self):
        for status in ("READY", "POSTED", "PUBLISH_OUTCOME_UNVERIFIED", "FAILED"):
            c = FakeClient()
            c.ws.rows[0]["status"] = status
            with self.subTest(status=status), self.assertRaisesRegex(
                PermissionError, "source_changed",
            ):
                write(c)
            self.assertFalse(c.ws.writes)

    def test_wrong_result_identity_or_draft_fails_before_write(self):
        c = FakeClient()
        c.ws.rows[0]["result_id"] = "conflicting_result"
        with self.assertRaisesRegex(PermissionError, "source_changed"):
            write(c)
        self.assertFalse(c.ws.writes)
        c = FakeClient()
        with self.assertRaisesRegex(PermissionError, "source_changed"):
            write(c, expected_draft_id="other-draft")
        self.assertFalse(c.ws.writes)

    def test_wrong_account_text_platform_fails_before_write(self):
        for key, value in (("account_id", "night_scout"),
                           ("public_post_text", "違う文章"),
                           ("platform", "x")):
            c = FakeClient()
            c.ws.rows[0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(
                PermissionError, "source_changed",
            ):
                write(c)
            self.assertFalse(c.ws.writes)

    def test_duplicate_schema_or_missing_column_refused(self):
        c = FakeClient()
        c.ws.headers.append("queue_id")
        with self.assertRaisesRegex(PermissionError, "schema_unverified"):
            write(c)
        self.assertFalse(c.ws.writes)
        c = FakeClient()
        c.ws.headers.remove("result_id")
        with self.assertRaisesRegex(PermissionError, "schema_unverified"):
            write(c)
        self.assertFalse(c.ws.writes)

    def test_dry_run_no_writer_side_effect(self):
        c = FakeClient()
        c.dry_run = True
        with self.assertRaisesRegex(PermissionError, "dry_run_forbidden"):
            write(c)
        self.assertFalse(c.ws.writes)

    def test_ambiguous_ack_not_retried(self):
        c = FakeClient()
        c.ws.raise_during_write = True
        with self.assertRaisesRegex(RuntimeError, "ambiguous remote write"):
            write(c)
        self.assertEqual(len(c.ws.writes), 1)
        self.assertEqual(c.ws.rows[0]["status"], "POSTED_SAVE_FAILED")

    def test_readback_mismatch_never_replays(self):
        c = FakeClient()
        c.ws.forbid_commit = True
        with self.assertRaisesRegex(RuntimeError, "readback_unverified"):
            write(c)
        self.assertEqual(len(c.ws.writes), 1)
        self.assertEqual(c.ws.rows[0]["status"], "POSTED_SAVE_FAILED")


if __name__ == "__main__":
    unittest.main()
