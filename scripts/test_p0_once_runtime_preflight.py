#!/usr/bin/env python3
"""No-network, read-only regression for the VPS one-use runtime preflight."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))
from p0_real_delivery_once import (
    P0OnceBlocked, P0OnceGuard, initialize_local_db, source_fingerprint,
)
import validate_p0_once_runtime as preflight

ACCOUNT = "night_scout"
QUEUE = "ns_host_gate_0001"
TEXT = "体験入店では働くペースと条件を整理して、無理なく続けられるか確認したい。"
KEY = bytes.fromhex("bd" * 32)


class ReadOnlyHostPreflight(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sns-p0-host-readonly-")
        self.addCleanup(self.temp.cleanup)
        self.file = str(Path(self.temp.name) / "ledger.sqlite3")
        initialize_local_db(self.file, explicit_operator_init=True, allow_test_path=True)
        self.ledger = P0OnceGuard(self.file, KEY, allow_test_path=True)
        self.sha = source_fingerprint(account_id=ACCOUNT, queue_id=QUEUE, text=TEXT)

    def test_empty_ledger_is_valid_without_mutation(self):
        before = Path(self.file).read_bytes()
        with patch.dict(os.environ, {"SNS_P0_ONCE_GATE_ENABLED": "true"}):
            report = preflight.inspect(self.ledger, account_id=ACCOUNT)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["verified_claims"], 0)
        self.assertEqual(report["verified_send_attempts"], 0)
        self.assertFalse(report["would_write"])
        self.assertEqual(before, Path(self.file).read_bytes())

    def test_real_claim_and_irreversible_send_reservation_validate(self):
        receipt = self.ledger.claim(
            account_id=ACCOUNT, queue_id=QUEUE, source_sha256=self.sha)
        self.ledger.consume_send_receipt(
            account_id=ACCOUNT, queue_id=QUEUE, text=TEXT,
            source_sha256=self.sha, event_mac=receipt["event_mac"])
        report = preflight.inspect(self.ledger, account_id=ACCOUNT)
        self.assertEqual(report["verified_claims"], 1)
        self.assertEqual(report["verified_send_attempts"], 1)
        self.ledger.provider_accepted(
            account_id=ACCOUNT, queue_id=QUEUE,
            source_sha256=self.sha, provider_post_id="synthetic_post")
        report = preflight.inspect(self.ledger, account_id=ACCOUNT)
        self.assertEqual(report["verified_send_attempts"], 1)

    def test_send_journal_tamper_is_detected(self):
        receipt = self.ledger.claim(
            account_id=ACCOUNT, queue_id=QUEUE, source_sha256=self.sha)
        self.ledger.consume_send_receipt(
            account_id=ACCOUNT, queue_id=QUEUE, text=TEXT,
            source_sha256=self.sha, event_mac=receipt["event_mac"])
        with sqlite3.connect(self.file) as db:
            db.execute("DROP TRIGGER sns_p0_once_send_no_update")
            db.execute("UPDATE sns_p0_once_send_attempts SET send_mac=?",
                       ("e" * 64,))
        with self.assertRaises(P0OnceBlocked):
            preflight.inspect(self.ledger, account_id=ACCOUNT)
        with sqlite3.connect(self.file) as db:
            db.execute("""CREATE TRIGGER sns_p0_once_send_no_update
                          BEFORE UPDATE ON sns_p0_once_send_attempts
                          BEGIN SELECT RAISE(ABORT,'p0_once_send_immutable'); END""")
        with self.assertRaisesRegex(P0OnceBlocked, "SEND_JOURNAL_INVALID"):
            preflight.inspect(self.ledger, account_id=ACCOUNT)

    def test_bad_event_mac_blocks(self):
        self.ledger.claim(account_id=ACCOUNT, queue_id=QUEUE,
                          source_sha256=self.sha)
        with sqlite3.connect(self.file) as db:
            db.execute("DROP TRIGGER sns_p0_once_events_no_update")
            db.execute("UPDATE sns_p0_once_events SET event_mac=?",
                       ("e" * 64,))
            db.execute("""CREATE TRIGGER sns_p0_once_events_no_update
                          BEFORE UPDATE ON sns_p0_once_events
                          BEGIN SELECT RAISE(ABORT,'p0_once_journal_immutable'); END""")
        with self.assertRaisesRegex(P0OnceBlocked, "JOURNAL"):
            preflight.inspect(self.ledger, account_id=ACCOUNT)

    def test_scope_and_activation_must_be_explicit(self):
        with self.assertRaisesRegex(P0OnceBlocked, "SCOPE_INVALID"):
            preflight.inspect(self.ledger, account_id="beauty_account")
        with patch.dict(os.environ, {"SNS_P0_ONCE_GATE_ENABLED": "false"}):
            with self.assertRaisesRegex(P0OnceBlocked, "GATE_DISABLED"):
                preflight.preflight(account_id=ACCOUNT)
        with patch.dict(os.environ, {"SNS_P0_ONCE_GATE_ENABLED": "true"}), patch(
            "validate_p0_once_runtime.P0OnceGuard.from_env",
            return_value=self.ledger,
        ):
            self.assertEqual(preflight.preflight(account_id=ACCOUNT)["status"],
                             "PASS")

    def test_fake_ledger_is_not_a_runtime_authority(self):
        class Fake:
            db_path = self.file
            allow_test_path = True
            secret_key = KEY
        with self.assertRaisesRegex(P0OnceBlocked, "SCOPE_INVALID"):
            preflight.inspect(Fake(), account_id=ACCOUNT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
