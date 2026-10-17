#!/usr/bin/env python3
"""No-network and no-source-write tests for the ephemeral P0 restore drill."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import p0_ledger_backup_restore_drill as drill
from p0_real_delivery_once import (
    P0OnceGuard, initialize_local_db, source_fingerprint,
)

KEY = bytes.fromhex("57" * 32)
QID = "night_recovery_drill_claim_001"
TXT = "発行しない監査用のサンプル文章"


class RestoreDrillTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="sns-test-p0-restore-")
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "p0.sqlite3"
        initialize_local_db(str(self.db), explicit_operator_init=True, allow_test_path=True)

    def ledger(self, *, key=KEY) -> P0OnceGuard:
        return P0OnceGuard(str(self.db), key, allow_test_path=True)

    def claim(self) -> tuple[str, str]:
        source = source_fingerprint(account_id="night_scout", queue_id=QID, text=TXT)
        receipt = self.ledger().claim(
            account_id="night_scout", queue_id=QID, source_sha256=source,
        )
        return source, receipt["event_mac"]

    def run_safely(self, *, key=KEY) -> dict:
        return drill.run_drill(str(self.db), key, allow_test_path=True)

    def test_empty_ledger_restores_but_never_authorizes_posting(self) -> None:
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        with patch("socket.socket", side_effect=AssertionError("NETWORK_CALL_FORBIDDEN")):
            report = self.run_safely()
        self.assertEqual(report["status"], "RESTORE_REHEARSAL_PASS_NO_CUTOVER")
        self.assertEqual(report["verified_claims"], 0)
        self.assertEqual(report["verified_send_attempts"], 0)
        self.assertTrue(report["restored_copy_signature_checked"])
        self.assertFalse(report["operator_backup_restore_attested"])
        self.assertFalse(report["durable_backup_retained"])
        self.assertFalse(report["publish_authorized"])
        self.assertFalse(report["sheets_write_authorized"])
        self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).hexdigest())

    def test_claim_and_immutable_send_attempt_survive_restore(self) -> None:
        source, mac = self.claim()
        self.ledger().consume_send_receipt(
            account_id="night_scout", queue_id=QID, text=TXT,
            source_sha256=source, event_mac=mac,
        )
        before = hashlib.sha256(self.db.read_bytes()).digest()
        report = self.run_safely()
        self.assertEqual(report["verified_claims"], 1)
        self.assertEqual(report["verified_send_attempts"], 1)
        self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).digest())
        with self.assertRaises(Exception):
            self.ledger().claim(account_id="night_scout", queue_id=QID, source_sha256=source)

    def test_wrong_hmac_key_cannot_attest_existing_claim(self) -> None:
        self.claim()
        with self.assertRaisesRegex(drill.DrillBlocked, "UNVERIFIABLE"):
            self.run_safely(key=bytes.fromhex("ab" * 32))

    def test_missing_and_alias_db_rejected(self) -> None:
        with self.assertRaisesRegex(drill.DrillBlocked, "UNTRUSTED"):
            drill.run_drill(str(self.db.parent / "missing.sqlite3"), KEY, allow_test_path=True)
        alias = self.db.parent / "alias.sqlite3"
        alias.symlink_to(self.db)
        with self.assertRaisesRegex(drill.DrillBlocked, "UNTRUSTED"):
            drill.run_drill(str(alias), KEY, allow_test_path=True)

    def test_file_permissions_and_source_parent_enforced(self) -> None:
        self.db.chmod(0o644)
        with self.assertRaisesRegex(drill.DrillBlocked, "UNTRUSTED"):
            self.run_safely()

    def test_existing_ledger_schema_tamper_fails_closed(self) -> None:
        with sqlite3.connect(str(self.db)) as con:
            con.execute("DROP TRIGGER sns_p0_once_events_no_delete")
        with self.assertRaisesRegex(drill.DrillBlocked, "UNVERIFIABLE"):
            self.run_safely()

    def test_invalid_key_is_rejected_without_source_access(self) -> None:
        with self.assertRaisesRegex(drill.DrillBlocked, "KEY_INVALID"):
            self.run_safely(key=b"short")

    def test_logical_snapshot_content_mismatch_blocks(self) -> None:
        self.claim()
        original = drill._logical_fingerprint
        visits = 0

        def changed(path):
            nonlocal visits
            visits += 1
            counts, signature = original(path)
            return counts, b"changed" if visits == 2 else signature

        with patch.object(drill, "_logical_fingerprint", side_effect=changed):
            with self.assertRaisesRegex(drill.DrillBlocked, "CONTENT_MISMATCH"):
                self.run_safely()

    def test_source_modified_during_backup_does_not_pass(self) -> None:
        original = drill._sqlite_backup
        calls = 0

        def modified(conn, output):
            nonlocal calls
            calls += 1
            original(conn, output)
            if calls == 1:
                st = self.db.stat()
                os.utime(self.db, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))

        with patch.object(drill, "_sqlite_backup", side_effect=modified):
            with self.assertRaisesRegex(drill.DrillBlocked, "SOURCE_MODIFIED"):
                self.run_safely()

    def test_original_ledger_never_reinitialized_and_no_scratch_persisted(self) -> None:
        self.claim()
        old = self.db.read_bytes()
        self.run_safely()
        self.assertEqual(old, self.db.read_bytes())
        self.assertEqual(sorted(p.name for p in self.db.parent.iterdir()), ["p0.sqlite3"])

    def test_output_contains_no_ledger_queue_provider_or_secret(self) -> None:
        self.claim()
        report = self.run_safely()
        serialized = str(report)
        self.assertNotIn(QID, serialized)
        self.assertNotIn(TXT, serialized)
        self.assertNotIn(KEY.hex(), serialized)
        self.assertNotIn(str(self.db), serialized)


if __name__ == "__main__":
    unittest.main()
