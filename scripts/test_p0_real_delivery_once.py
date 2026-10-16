#!/usr/bin/env python3
"""Adversarial tests for one-use real provider barrier; synthetic local SQLite."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import p0_real_delivery_once as core  # noqa: E402

KEY = bytes.fromhex("ab" * 32)
AC = "night_scout"
QID = "night_20261014_1500_text"
TEXT = "サンプルの安全な原稿です。"
SRC = core.source_fingerprint(account_id=AC, queue_id=QID, text=TEXT)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="p0-once-unit-")
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "ledger.sqlite3")
        core.initialize_local_db(self.path, explicit_operator_init=True,
                                 allow_test_path=True)
        self.ledger = core.P0OnceGuard(self.path, KEY, allow_test_path=True)

    def claim(self, *, qid=QID, account=AC, source=SRC):
        return self.ledger.claim(account_id=account, queue_id=qid,
                                 source_sha256=source)

    def ack(self, *, qid=QID, account=AC, source=SRC, provider_id="th_00001"):
        return self.ledger.provider_accepted(
            account_id=account, queue_id=qid, source_sha256=source,
            provider_post_id=provider_id)

    def verify(self, *, qid=QID, account=AC, source=SRC,
               queue_ok=True, result_ok=True, provider_id="th_00001"):
        return self.ledger.verify_posted(
            account_id=account, queue_id=qid, source_sha256=source,
            provider_post_id=provider_id, queue_readback_pass=queue_ok,
            result_readback_pass=result_ok)

    def inspect(self):
        return self.ledger.inspect(queue_id=QID)

    def test_claim_then_ack_then_verified_requires_two_readbacks(self):
        self.assertEqual(self.claim()["status"], "CLAIMED_UNCERTAIN")
        self.assertEqual(self.ack()["status"], "PROVIDER_ACKED")
        self.assertEqual(self.verify()["status"], "POSTED_VERIFIED")
        state = self.inspect()
        self.assertEqual(state["revision"], 3)
        self.assertTrue(state["provider_ack_recorded"])
        self.assertFalse(state["retry_allowed"])
        self.assertFalse(state["source_cutover_authorized"])

    def test_duplicate_claim_for_same_account_rejected(self):
        self.claim()
        with self.assertRaisesRegex(core.P0OnceBlocked, "NO_RETRY"):
            self.claim()

    def test_same_exact_text_different_queue_ids_cannot_race(self):
        self.claim()
        another="night_20261014_1600_text"
        same=core.source_fingerprint(account_id=AC,queue_id=another,text=TEXT)
        self.assertEqual(same,SRC)
        with self.assertRaisesRegex(core.P0OnceBlocked,"SAME_TEXT_ACCOUNT"):
            self.claim(qid=another,source=same)

    def test_same_exact_text_other_account_is_independent(self):
        self.claim()
        another="liver_20261014_1600_text"
        source=core.source_fingerprint(account_id="liver_manager",queue_id=another,text=TEXT)
        second=self.claim(qid=another,account="liver_manager",source=source)
        self.assertEqual(second["status"],"CLAIMED_UNCERTAIN")

    def test_queue_ids_are_globally_unique_cross_account(self):
        self.claim()
        with self.assertRaisesRegex(core.P0OnceBlocked, "COLLISION"):
            self.claim(account="liver_manager")

    def test_text_changed_after_claim_rejected(self):
        self.claim()
        other = core.source_fingerprint(account_id=AC, queue_id=QID, text=TEXT+"改変")
        with self.assertRaisesRegex(core.P0OnceBlocked, "COLLISION"):
            self.ack(source=other)

    def test_absent_or_malformed_ack_stays_terminal_for_resend(self):
        self.claim()
        with self.assertRaisesRegex(core.P0OnceBlocked, "ACK_MISSING"):
            self.ack(provider_id="")
        with self.assertRaises(core.P0OnceBlocked):
            self.ack(provider_id="http://api.example/foo")
        with self.assertRaisesRegex(core.P0OnceBlocked, "NO_RETRY"):
            self.claim()
        self.assertEqual(self.inspect()["status"], "CLAIMED_UNCERTAIN")

    def test_unknown_outcome_never_reopens(self):
        self.claim()
        self.ledger.quarantine(account_id=AC, queue_id=QID,
                               source_sha256=SRC)
        for call in (self.claim, self.ack, self.verify):
            with self.subTest(call=call.__name__), self.assertRaises(core.P0OnceBlocked):
                call()
        self.assertEqual(self.inspect()["status"], "PROVIDER_OUTCOME_UNVERIFIED")

    def test_ack_requires_prior_claim(self):
        with self.assertRaises(core.P0OnceBlocked):
            self.ack()
        with self.assertRaises(core.P0OnceBlocked):
            self.verify()

    def test_verify_requires_both_readbacks(self):
        self.claim()
        self.ack()
        for flags in ((False, True), (True, False), (False, False)):
            with self.subTest(flags=flags), self.assertRaisesRegex(
                core.P0OnceBlocked, "READBACK_REQUIRED"
            ):
                self.verify(queue_ok=flags[0], result_ok=flags[1])
        self.assertEqual(self.inspect()["status"], "PROVIDER_ACKED")
        self.verify()

    def test_cannot_reverify_or_ack_after_finished(self):
        self.claim()
        self.ack()
        self.verify()
        for action in (self.claim, self.ack, self.verify):
            with self.assertRaises(core.P0OnceBlocked):
                action()

    def test_provider_id_must_match_and_be_unique(self):
        self.claim()
        self.ack()
        with self.assertRaisesRegex(core.P0OnceBlocked, "MISMATCH"):
            self.verify(provider_id="th_99999")
        other_qid = "night_20261014_1700_text"
        other_source = core.source_fingerprint(account_id=AC,queue_id=other_qid,text="another")
        self.claim(qid=other_qid,source=other_source)
        with self.assertRaises(core.P0OnceBlocked):
            self.ack(qid=other_qid,source=other_source)
        with self.assertRaises(core.P0OnceBlocked):
            self.claim(qid=other_qid,source=other_source)
        self.assertEqual(self.ledger.inspect(queue_id=other_qid)["status"],
                         "CLAIMED_UNCERTAIN")

    def test_two_threads_two_db_connections_race_one_wins(self):
        pair = threading.Barrier(2)
        results = []
        mutex = threading.Lock()
        def worker():
            guard = core.P0OnceGuard(self.path, KEY, allow_test_path=True)
            pair.wait(timeout=8)
            try:
                outcome = guard.claim(account_id=AC, queue_id=QID,source_sha256=SRC)
                outcome = outcome["status"]
            except core.P0OnceBlocked:
                outcome = "BLOCKED"
            with mutex:
                results.append(outcome)
        jobs = [threading.Thread(target=worker, daemon=True) for _ in range(2)]
        for job in jobs: job.start()
        for job in jobs: job.join(timeout=10)
        self.assertEqual(sorted(results), ["BLOCKED", "CLAIMED_UNCERTAIN"])

    def test_journal_is_immutable(self):
        self.claim()
        with sqlite3.connect(self.path) as db:
            for statement in (
                "UPDATE sns_p0_once_events SET action='ACK' WHERE event_id=1",
                "DELETE FROM sns_p0_once_events WHERE event_id=1",
                "DELETE FROM sns_p0_once_heads",
            ):
                with self.subTest(sql=statement), self.assertRaises(sqlite3.DatabaseError):
                    db.execute(statement)

    def test_head_tamper_detected(self):
        self.claim()
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE sns_p0_once_heads SET last_event_mac=?", ("f"*64,))
        with self.assertRaisesRegex(core.P0OnceBlocked, "JOURNAL_HEAD_MISMATCH"):
            self.inspect()

    def test_journal_payload_tamper_fails_hmac_verification(self):
        self.claim()
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TRIGGER sns_p0_once_events_no_update")
            db.execute("UPDATE sns_p0_once_events SET payload_json='{}' WHERE event_id=1")
        with self.assertRaises(core.P0OnceBlocked):
            self.inspect()

    def test_wrong_signing_key_rejected(self):
        self.claim()
        guard = core.P0OnceGuard(self.path, b"z"*32, allow_test_path=True)
        with self.assertRaisesRegex(core.P0OnceBlocked, "JOURNAL_CORRUPT"):
            guard.inspect(queue_id=QID)

    def test_removing_event_cannot_pass_integrity(self):
        self.claim()
        with sqlite3.connect(self.path) as db:
            db.execute("DROP TRIGGER sns_p0_once_events_no_delete")
            db.execute("DELETE FROM sns_p0_once_events")
        with self.assertRaises(core.P0OnceBlocked):
            self.inspect()

    def test_missing_db_never_auto_reinitialized(self):
        Path(self.path).unlink()
        with self.assertRaisesRegex(core.P0OnceBlocked, "FILE_MISSING"):
            self.ledger.inspect(queue_id=QID)
        self.assertFalse(Path(self.path).exists())

    def test_cannot_reinitialize_existing_file(self):
        with self.assertRaisesRegex(core.P0OnceBlocked, "ALREADY_EXISTS"):
            core.initialize_local_db(self.path, explicit_operator_init=True,
                                     allow_test_path=True)

    def test_private_db_permissions_enforced(self):
        os.chmod(self.path, 0o644)
        with self.assertRaisesRegex(core.P0OnceBlocked, "PERMISSIONS_UNSAFE"):
            self.claim()

    def test_symlink_path_forbidden(self):
        symlink = str(Path(self.tmp.name)/"alias.sqlite3")
        Path(symlink).symlink_to(self.path)
        with self.assertRaisesRegex(core.P0OnceBlocked, "SYMLINK"):
            core.P0OnceGuard(symlink, KEY, allow_test_path=True)

    def test_media_content_and_beauty_are_blocked(self):
        for kwargs in (
            {"account_id": "beauty_account", "queue_id": QID, "text": TEXT},
            {"account_id": AC, "queue_id": QID, "text": TEXT, "media_used": True},
            {"account_id": AC, "queue_id": "", "text": TEXT},
            {"account_id": AC, "queue_id": QID, "text": ""},
        ):
            with self.subTest(case=kwargs), self.assertRaises(core.P0OnceBlocked):
                core.source_fingerprint(**kwargs)

    def test_no_source_text_or_secret_in_sqlite(self):
        self.claim()
        self.ack()
        db_bytes = Path(self.path).read_bytes()
        self.assertNotIn(TEXT.encode(), db_bytes)
        self.assertNotIn(KEY, db_bytes)

    def test_operation_id_is_unique_and_event_chain_verifiable(self):
        self.claim()
        self.ack()
        self.verify()
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT operation_id,previous_event_mac,event_mac "
                              "FROM sns_p0_once_events ORDER BY revision").fetchall()
        self.assertEqual(len({r[0] for r in rows}), 3)
        self.assertEqual(rows[0][1], core.ZERO_MAC)
        self.assertEqual(rows[1][1], rows[0][2])
        self.assertEqual(rows[2][1], rows[1][2])

    def test_read_only_inspect_missing_queue_does_not_create(self):
        with self.assertRaisesRegex(core.P0OnceBlocked, "QUEUE_NOT_FOUND"):
            self.inspect()
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sns_p0_once_events").fetchone()[0],0)

    def test_environment_disabled_not_implicitly_authorized(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(core.P0OnceBlocked, "HMAC_KEY_NOT_CONFIGURED"):
                core.P0OnceGuard.from_env()

    def test_test_db_location_requires_explicit_test_flag(self):
        with self.assertRaisesRegex(core.P0OnceBlocked, "EPHEMERAL_LOCATION"):
            core.P0OnceGuard(self.path, KEY)

    def test_init_requires_explicit_opt_in(self):
        new = str(Path(self.tmp.name) / "new.sqlite3")
        with self.assertRaisesRegex(core.P0OnceBlocked, "OPERATOR_INIT_REQUIRED"):
            core.initialize_local_db(new, explicit_operator_init=False,
                                     allow_test_path=True)
        self.assertFalse(Path(new).exists())

    def test_no_untrusted_provider_id_or_unbounded_queue_id(self):
        self.claim()
        with self.assertRaises(core.P0OnceBlocked):
            self.ack(provider_id="bad id\nSECRET")
        with self.assertRaises(core.P0OnceBlocked):
            self.claim(qid="x" * 180)


if __name__ == "__main__":
    unittest.main(verbosity=2)
