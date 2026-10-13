#!/usr/bin/env python3
"""SQLite synthetic P0 CAS, audit, concurrency, and no-publish tests."""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from p0_queue_cas_rehearsal import (  # noqa: E402
    P0QueueRehearsal, P0RehearsalBlocked, initialize_rehearsal_schema,
)
from rehearse_p0_queue_cas import demo  # noqa: E402

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
SOURCE = "a" * 64
Q = "test_p0_candidate"
A = "night_scout"
OBS = "p0_observation_synthetic_00001"
CLM = "p0_claim_synthetic_000000001"
UNK = "p0_uncertain_synthetic_00001"


class P0OfflineCAS(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.db.execute("PRAGMA foreign_keys=ON")
        initialize_rehearsal_schema(self.db, explicit_local_test_only=True)
        self.ledger = P0QueueRehearsal(self.db)

    def tearDown(self):
        self.db.close()

    def observe(self, **kw):
        args = dict(
            account_id=A, queue_id=Q, platform="threads",
            source_sha256=SOURCE, observed_at=NOW, as_of=NOW, operation_id=OBS,
        )
        args.update(kw)
        return self.ledger.observe(**args)

    def claim(self, obs=None, **kw):
        if obs is None:
            obs = self.ledger.inspect(queue_id=Q)
        args = dict(
            account_id=A, queue_id=Q, operation_id=CLM,
            expected_revision=obs["revision"],
            expected_head_sha256=obs["head_sha256"],
            expected_source_sha256=SOURCE, as_of=NOW,
        )
        args.update(kw)
        return self.ledger.claim(**args)

    def test_missing_migration_and_implicit_setup_rejected(self):
        empty = sqlite3.connect(":memory:", isolation_level=None)
        empty.execute("PRAGMA foreign_keys=ON")
        try:
            with self.assertRaisesRegex(P0RehearsalBlocked, "P0_SCHEMA_MISSING"):
                P0QueueRehearsal(empty).inspect(queue_id=Q)
            with self.assertRaisesRegex(P0RehearsalBlocked, "P0_LOCAL_MIGRATION_NOT_AUTHORIZED"):
                initialize_rehearsal_schema(empty)
        finally:
            empty.close()

    def test_observe_claim_unknown_never_permit_real_post(self):
        observed = self.observe()
        self.assertEqual(observed["status"], "OBSERVED_BLOCKED")
        claimed = self.claim(observed)
        self.assertEqual(claimed["status"], "CLAIMED_BLOCKED")
        unknown = self.ledger.quarantine(
            account_id=A, queue_id=Q, operation_id=UNK,
            expected_revision=claimed["revision"],
            expected_head_sha256=claimed["head_sha256"],
            reason="ACK_UNKNOWN", as_of=NOW,
        )
        self.assertEqual(unknown["status"], "OUTCOME_UNKNOWN_BLOCKED")
        self.assertEqual(unknown, self.ledger.inspect(queue_id=Q))
        for stage in (observed, claimed, unknown):
            self.assertFalse(stage["publish_authorized"])
            self.assertFalse(stage["dispatch_allowed"])
            self.assertFalse(stage["sheets_write_allowed"])
            self.assertFalse(stage["source_cutover_authorized"])
            self.assertFalse(stage["network_called"])
            self.assertNotIn(Q, str(stage))

    def test_repeated_claim_and_unknown_outcome_are_never_reissued(self):
        observed = self.observe()
        self.claim(observed)
        for kwargs in (
            {},
            {"operation_id": "p0_claim_retry_synthetic_001"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(P0RehearsalBlocked):
                self.claim(observed, **kwargs)
        self.assertEqual(
            self.ledger.inspect(queue_id=Q)["status"], "CLAIMED_BLOCKED",
        )

    def test_wrong_account_global_queue_collision_blocks(self):
        self.observe()
        with self.assertRaisesRegex(P0RehearsalBlocked, "GLOBAL_QUEUE_ID_ALREADY_USED"):
            self.observe(account_id="liver_manager", operation_id="p0_other_account_synthetic_001")
        with self.assertRaisesRegex(P0RehearsalBlocked, "ACCOUNT_SCOPE_MISMATCH"):
            self.claim(account_id="liver_manager")

    def test_stale_hash_version_and_timestamp_fail_closed(self):
        observed = self.observe()
        for expected in (
            {"expected_revision": 9},
            {"expected_head_sha256": "b" * 64},
            {"expected_source_sha256": "b" * 64},
            {"as_of": NOW + timedelta(seconds=91)},
            {"as_of": NOW - timedelta(seconds=1)},
        ):
            with self.subTest(expected=expected), self.assertRaises(P0RehearsalBlocked):
                self.claim(observed, **expected)
        self.assertEqual(
            self.ledger.inspect(queue_id=Q)["status"], "OBSERVED_BLOCKED",
        )

    def test_observe_stale_source_and_restricted_scope(self):
        for bad in (
            {"source_sha256": "not a sha"},
            {"observed_at": NOW - timedelta(minutes=10)},
            {"observed_at": NOW + timedelta(seconds=1)},
            {"platform": "x"},
            {"account_id": "beauty_account"},
            {"queue_id": "=HYPERLINK(data)"},
            {"operation_id": "q"},
        ):
            with self.subTest(bad=bad), self.assertRaises(P0RehearsalBlocked):
                self.observe(**bad)
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM sns_p0_rehearsal_heads").fetchone()[0], 0,
        )

    def test_cancel_only_before_claim_never_reopens(self):
        observed = self.observe()
        result = self.ledger.cancel_unclaimed(
            account_id=A, queue_id=Q, operation_id="p0_cancel_synthetic_00001",
            expected_revision=observed["revision"],
            expected_head_sha256=observed["head_sha256"], as_of=NOW,
        )
        self.assertEqual(result["status"], "CANCELLED_BLOCKED")
        with self.assertRaises(P0RehearsalBlocked):
            self.claim(result)
        with self.assertRaises(P0RehearsalBlocked):
            self.observe(operation_id="p0_retry_observe_synthetic_01")

    def test_postclaim_cancel_and_unknown_resume_are_denied(self):
        self.observe()
        claimed = self.claim()
        with self.assertRaisesRegex(P0RehearsalBlocked, "REPLAY_OR_TERMINAL_STATE"):
            self.ledger.cancel_unclaimed(
                account_id=A, queue_id=Q, operation_id="p0_cancel_claimed_synthetic_01",
                expected_revision=claimed["revision"],
                expected_head_sha256=claimed["head_sha256"], as_of=NOW,
            )
        unknown = self.ledger.quarantine(
            account_id=A, queue_id=Q, operation_id=UNK,
            expected_revision=claimed["revision"],
            expected_head_sha256=claimed["head_sha256"],
            reason="ACK_UNKNOWN", as_of=NOW,
        )
        with self.assertRaises(P0RehearsalBlocked):
            self.claim(unknown, as_of=NOW + timedelta(days=10),
                       operation_id="p0_claim_expired_synthetic_01")

    def test_invalid_uncertain_reason_and_post_authorize_block(self):
        self.observe()
        claimed = self.claim()
        with self.assertRaisesRegex(P0RehearsalBlocked, "REASON_INVALID"):
            self.ledger.quarantine(
                account_id=A, queue_id=Q, operation_id=UNK,
                expected_revision=claimed["revision"],
                expected_head_sha256=claimed["head_sha256"],
                reason="client secrets in the error", as_of=NOW,
            )
        with self.assertRaisesRegex(P0RehearsalBlocked, "CAN_NEVER_AUTHORIZE_POST"):
            self.ledger.authorize_external_post(token="test", post=True)

    def test_event_triggers_prevent_update_and_delete(self):
        self.observe()
        for statement in (
            "DELETE FROM sns_p0_rehearsal_events",
            "UPDATE sns_p0_rehearsal_events SET action='CLAIM'",
            "DELETE FROM sns_p0_rehearsal_heads",
        ):
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(statement)
        self.assertEqual(self.ledger.inspect(queue_id=Q)["status"], "OBSERVED_BLOCKED")

    def test_head_mutation_detected_by_history_validation(self):
        self.observe()
        self.db.execute(
            "UPDATE sns_p0_rehearsal_heads SET state='CANCELLED_BLOCKED' WHERE queue_id=?",
            (Q,),
        )
        with self.assertRaisesRegex(P0RehearsalBlocked, "HEAD_TAMPERED"):
            self.ledger.inspect(queue_id=Q)
        with self.assertRaises(P0RehearsalBlocked):
            self.claim()

    def test_mid_transaction_event_failure_rolls_back_head(self):
        self.db.execute(
            """CREATE TRIGGER synthetic_reject_p0_event
               BEFORE INSERT ON sns_p0_rehearsal_events
               BEGIN SELECT RAISE(ABORT,'synthetic injection'); END"""
        )
        with self.assertRaisesRegex(P0RehearsalBlocked, "SQLITE_OUTCOME_UNKNOWN"):
            self.observe()
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM sns_p0_rehearsal_heads").fetchone()[0], 0,
        )

    def test_duplicate_operation_id_is_not_replayed(self):
        self.observe()
        with self.assertRaises(P0RehearsalBlocked):
            self.observe(queue_id="another_synthetic_p0_candidate")
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM sns_p0_rehearsal_heads").fetchone()[0], 1,
        )

    def test_database_transaction_and_foreign_keys_required(self):
        self.observe()
        self.db.execute("BEGIN")
        try:
            with self.assertRaisesRegex(P0RehearsalBlocked, "DATABASE_UNAVAILABLE"):
                self.ledger.inspect(queue_id=Q)
        finally:
            self.db.execute("ROLLBACK")
        self.db.execute("PRAGMA foreign_keys=OFF")
        with self.assertRaisesRegex(P0RehearsalBlocked, "FOREIGN_KEYS_OFF"):
            self.ledger.inspect(queue_id=Q)

    def test_cross_connection_claim_is_one_use(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "concurrent.sqlite3")
            seed = sqlite3.connect(path, isolation_level=None)
            seed.execute("PRAGMA foreign_keys=ON")
            initialize_rehearsal_schema(seed, explicit_local_test_only=True)
            original = P0QueueRehearsal(seed).observe(
                account_id=A, queue_id=Q, platform="threads",
                source_sha256=SOURCE, observed_at=NOW, as_of=NOW,
                operation_id=OBS,
            )
            seed.close()
            barrier = threading.Barrier(2)
            results = []
            lock = threading.Lock()

            # Give both contenders the SAME expected CAS and distinct ops.
            def worker(number: int):
                db = sqlite3.connect(path, isolation_level=None, timeout=4.0)
                db.execute("PRAGMA foreign_keys=ON")
                try:
                    barrier.wait(timeout=3.0)
                    try:
                        state = P0QueueRehearsal(db).claim(
                            account_id=A, queue_id=Q,
                            operation_id=f"p0_parallel_claim_synthetic_{number:02d}",
                            expected_revision=original["revision"],
                            expected_head_sha256=original["head_sha256"],
                            expected_source_sha256=SOURCE, as_of=NOW,
                        )
                        outcome = ("claimed", state["status"])
                    except P0RehearsalBlocked as error:
                        outcome = ("blocked", str(error))
                    with lock:
                        results.append(outcome)
                finally:
                    db.close()

            threads = [threading.Thread(target=worker, args=(n,)) for n in (1, 2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=8)
            self.assertFalse(any(t.is_alive() for t in threads))
            self.assertEqual(len(results), 2)
            self.assertEqual(sum(status == "claimed" for status, _ in results), 1)
            self.assertEqual(sum(status == "blocked" for status, _ in results), 1)
            check = sqlite3.connect(path, isolation_level=None)
            check.execute("PRAGMA foreign_keys=ON")
            self.assertEqual(
                P0QueueRehearsal(check).inspect(queue_id=Q)["status"],
                "CLAIMED_BLOCKED",
            )
            self.assertEqual(
                check.execute("SELECT COUNT(*) FROM sns_p0_rehearsal_events").fetchone()[0],
                2,
            )
            check.close()

    def test_demo_never_promotes_or_returns_private_identifiers(self):
        report = demo()
        self.assertEqual(report["status"], "CUTOVER_BLOCKED")
        self.assertEqual(report["provider_api_calls"], 0)
        self.assertEqual(report["legacy_inventory_status"], "CUTOVER_BLOCKED")
        self.assertGreater(report["remaining_legacy_p0_write_calls"], 0)
        self.assertGreaterEqual(report["remaining_legacy_total_write_calls"],
                                report["remaining_legacy_p0_write_calls"])
        self.assertTrue(report["replay_blocked"])
        self.assertFalse(report["publish_authorized"])
        self.assertFalse(report["sheets_write_allowed"])
        self.assertNotIn("synthetic_p0_candidate", json.dumps(report))
        self.assertEqual(report["stages"], [
            "OBSERVED_BLOCKED", "CLAIMED_BLOCKED", "OUTCOME_UNKNOWN_BLOCKED",
        ])


if __name__ == "__main__":
    unittest.main()
