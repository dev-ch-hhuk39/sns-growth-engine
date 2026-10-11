#!/usr/bin/env python3
"""Offline 5B-5C journal, external-drift, replay, rollback and no-publish tests."""
from __future__ import annotations

import copy
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_review_queue_reconciliation import (  # noqa: E402
    QueueReconciliationBlocked, ReviewQueueReconciliation,
    initialize_reconciliation_schema, queue_fingerprint,
)
from media_review_transactional_ledger import (  # noqa: E402
    ReviewLedgerBlocked, initialize_review_schema, record_review,
    revoke_review, verify_ledger_integrity,
)
from test_media_review_trusted_precommit import (  # noqa: E402
    AUTHORIZATION, ISSUER, NOW, FakeIdentityVerifier,
    FakeCanonicalReader, good_context, good_request,
)

KEY = ("liver_manager", "lm_1800_clip_media", "clip_001")
REVIEW_OPERATION = "op_review_reconciliation_00001"
REVOKE_OPERATION = "op_revoke_reconciliation_00001"


def setup_db(name=":memory:"):
    db = sqlite3.connect(name, isolation_level=None, timeout=2)
    initialize_review_schema(db)
    initialize_reconciliation_schema(db)
    return db


class FailingReader:
    def load_current(self, account_id, slot_id, queue_id):
        raise OSError("backend_access_token_and_private_path")


class QueueReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.db = setup_db()
        self.guard = ReviewQueueReconciliation(self.db)
        self.ctx = good_context()
        self.req = replace(
            good_request(self.ctx),
            expected_queue_sha256=queue_fingerprint(self.ctx.queue),
        )
        self.identity = FakeIdentityVerifier()
        self.source = FakeCanonicalReader(self.ctx)

    def tearDown(self):
        self.db.close()

    def record(self, *, guard=True, operation=REVIEW_OPERATION, context=None, request=None):
        return record_review(
            self.db, request or self.req, AUTHORIZATION,
            verifier=self.identity, canonical=FakeCanonicalReader(context or self.ctx),
            trusted_issuer=ISSUER, operation_id=operation, expected_ledger_version=0,
            queue_authority=self.guard if guard else None, as_of=NOW,
        )

    def revoke(self, operation=REVOKE_OPERATION):
        return revoke_review(
            self.db, self.req, AUTHORIZATION,
            verifier=self.identity, trusted_issuer=ISSUER,
            operation_id=operation, expected_ledger_version=1,
            reason_code="consent_withdrawn", queue_authority=self.guard, as_of=NOW,
        )

    def count(self, table):
        return self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_migration_fails_closed_without_existing_review_ledger(self):
        empty = sqlite3.connect(":memory:", isolation_level=None)
        try:
            with self.assertRaisesRegex(
                QueueReconciliationBlocked, "review_ledger_migration_required"
            ):
                initialize_reconciliation_schema(empty)
            self.assertIsNone(empty.execute(
                "SELECT name FROM sqlite_master WHERE name='sns_media_review_queue_bindings'"
            ).fetchone())
        finally:
            empty.close()

    def test_no_binding_is_never_a_publish_authority(self):
        state = self.guard.barrier(*KEY)
        self.assertEqual(state["state"], "NO_BINDING")
        self.assertIs(state["publish_authorized"], False)
        self.assertEqual(self.guard.pending_candidates(), [])

    def test_review_and_queue_binding_commit_in_one_sqlite_transaction(self):
        result = self.record()
        self.assertEqual(result["status"], "ISOLATED_REVIEW_LEDGER_RECORDED_NOT_AUTHORIZED")
        self.assertEqual(result["ledger_version"], 1)
        self.assertFalse(result["publish_authorized"])
        self.assertEqual(self.count("sns_media_review_events"), 1)
        self.assertEqual(self.count("sns_media_review_queue_bindings"), 1)
        self.assertEqual(self.count("sns_media_review_queue_reconciliation_events"), 1)
        bound = self.guard.barrier(*KEY)
        self.assertEqual(bound["state"], "REVIEW_RECORDED_BLOCKED")
        self.assertEqual(bound["reconciliation_state"], "PENDING")
        self.assertEqual(self.guard.pending_candidates(), [(*KEY, 1)])
        self.assertFalse(bound["effective_approval"])
        self.assertFalse(bound["publish_authorized"])
        payload = self.db.execute(
            "SELECT payload_json FROM sns_media_review_queue_reconciliation_events",
        ).fetchone()[0]
        for secret in (AUTHORIZATION, "PRIVATE_POST_BODY", "SENSITIVE_EVIDENCE",
                       "secret.example", "raw_evidence_text"):
            self.assertNotIn(secret, payload)

    def test_trusted_same_queue_revision_and_content_remains_blocked(self):
        self.record()
        before = copy.deepcopy(self.ctx)
        result = self.guard.reconcile_once(
            key=KEY, source=self.source,
            operation_id="sync_match_000000000001", expected_binding_version=1,
            as_of=NOW,
        )
        self.assertEqual(result["status"], "MATCHED_BLOCKED")
        self.assertTrue(result["source_matched_at_check"])
        self.assertFalse(result["effective_approval"])
        self.assertFalse(result["publish_authorized"])
        self.assertFalse(result["external_queue_atomicity_guaranteed"])
        # A previous match is never final: it must remain eligible for polling.
        self.assertEqual(self.guard.pending_candidates(), [(*KEY, 2)])
        self.assertEqual(self.ctx, before)
        self.assertEqual(self.guard.barrier(*KEY)["binding_version"], 2)

    def test_repeated_unchanged_checks_do_not_fill_history(self):
        self.record()
        first = self.guard.reconcile_once(
            key=KEY, source=self.source,
            operation_id="sync_match_000000000001",
            expected_binding_version=1, as_of=NOW,
        )
        self.assertEqual(first["binding_version"], 2)
        for index in range(3):
            refreshed = self.guard.reconcile_once(
                key=KEY, source=self.source,
                operation_id=f"sync_poll_00000000000{index}",
                expected_binding_version=2, as_of=NOW,
            )
            self.assertEqual(refreshed["status"], "MATCHED_BLOCKED")
            self.assertEqual(refreshed["binding_version"], 2)
            self.assertFalse(refreshed["publish_authorized"])
        self.assertEqual(self.count("sns_media_review_queue_reconciliation_events"), 2)

    def test_same_revision_but_changed_caption_cannot_be_silent(self):
        self.record()
        self.ctx.queue["public_post_text"] = "changed after review"
        result = self.guard.reconcile_once(
            key=KEY, source=self.source,
            operation_id="sync_drift_000000000001", expected_binding_version=1,
            as_of=NOW,
        )
        self.assertEqual(result["status"], "CONFLICT_BLOCKED")
        self.assertTrue(result["quarantined"])
        self.assertEqual(self.guard.barrier(*KEY)["state"], "DRIFT_QUARANTINED")
        # Returning to the original snapshot does not silently lift quarantine.
        with self.assertRaisesRegex(QueueReconciliationBlocked, "queue_already_blocked"):
            self.guard.reconcile_once(
                key=KEY, source=FakeCanonicalReader(good_context()),
                operation_id="sync_replay_after_drift001", expected_binding_version=2,
                as_of=NOW,
            )
        self.assertFalse(self.guard.barrier(*KEY)["publish_authorized"])

    def test_revoked_original_proof_changes_context_even_with_same_queue(self):
        self.record()
        self.ctx.evidence_by_id[next(iter(self.ctx.evidence_by_id))]["revoked"] = True
        result = self.guard.reconcile_once(
            key=KEY, source=self.source,
            operation_id="sync_rights_drift_00000001", expected_binding_version=1,
            as_of=NOW,
        )
        self.assertEqual(result["status"], "CONFLICT_BLOCKED")
        self.assertTrue(result["quarantined"])
        self.assertFalse(self.guard.barrier(*KEY)["publish_authorized"])

    def test_expired_verification_quarantines_identical_snapshots(self):
        self.record()
        # Proof metadata unchanged, but verification older than allowed 24h.
        result = self.guard.reconcile_once(
            key=KEY, source=self.source,
            operation_id="sync_stale_proof_00000001", expected_binding_version=1,
            as_of=NOW + timedelta(hours=26),
        )
        self.assertEqual(result["status"], "CONFLICT_BLOCKED")
        self.assertEqual(self.guard.barrier(*KEY)["state"], "DRIFT_QUARANTINED")

    def test_changed_review_plan_or_receipts_violates_snapshot_binding(self):
        for part in ("plan", "receipts"):
            with self.subTest(part=part):
                db = setup_db()
                guard = ReviewQueueReconciliation(db)
                context = good_context()
                request = replace(
                    good_request(context),
                    expected_queue_sha256=queue_fingerprint(context.queue),
                )
                record_review(
                    db, request, AUTHORIZATION,
                    verifier=FakeIdentityVerifier(),
                    canonical=FakeCanonicalReader(context),
                    trusted_issuer=ISSUER, operation_id=REVIEW_OPERATION,
                    expected_ledger_version=0, queue_authority=guard, as_of=NOW,
                )
                if part == "plan":
                    context.plan["source_tamper"] = "different"
                else:
                    context.receipts["source_tamper"] = "different"
                result = guard.reconcile_once(
                    key=KEY, source=FakeCanonicalReader(context),
                    operation_id="sync_changed_draft_00000001",
                    expected_binding_version=1, as_of=NOW,
                )
                self.assertEqual(result["status"], "CONFLICT_BLOCKED")
                self.assertTrue(result["quarantined"])
                db.close()

    def test_source_revision_change_and_permission_loss_quarantine(self):
        for mutation in (
            {"revision": "rev_new_revision"},
            {"status": "POSTED"},
            {"rights_status": "DENIED"},
            {"media_asset_id": "different_asset"},
            {"source_id": "different_source"},
        ):
            with self.subTest(mutation=mutation):
                db = setup_db()
                guard = ReviewQueueReconciliation(db)
                ctx = good_context()
                req = replace(good_request(ctx), expected_queue_sha256=queue_fingerprint(ctx.queue))
                record_review(
                    db, req, AUTHORIZATION,
                    verifier=FakeIdentityVerifier(), canonical=FakeCanonicalReader(ctx),
                    trusted_issuer=ISSUER, operation_id=REVIEW_OPERATION,
                    expected_ledger_version=0, queue_authority=guard, as_of=NOW,
                )
                ctx.queue.update(mutation)
                result = guard.reconcile_once(
                    key=KEY, source=FakeCanonicalReader(ctx),
                    operation_id="sync_drift_000000000002", expected_binding_version=1,
                    as_of=NOW,
                )
                self.assertTrue(result["quarantined"])
                self.assertFalse(guard.barrier(*KEY)["publish_authorized"])
                db.close()

    def test_unavailable_source_quarantines_without_leaking_backend(self):
        self.record()
        result = self.guard.reconcile_once(
            key=KEY, source=FailingReader(),
            operation_id="sync_unavailable_00000001", expected_binding_version=1,
            as_of=NOW,
        )
        self.assertEqual(result["status"], "CONFLICT_BLOCKED")
        self.assertEqual(self.guard.barrier(*KEY)["state"], "DRIFT_QUARANTINED")
        history = self.db.execute(
            "SELECT payload_json FROM sns_media_review_queue_reconciliation_events ORDER BY binding_version DESC LIMIT 1",
        ).fetchone()[0]
        self.assertNotIn("backend_access_token", history)

    def test_stale_expected_hash_blocks_even_if_queue_revision_unchanged(self):
        self.ctx.queue["public_post_text"] = "different draft, same revision"
        with self.assertRaisesRegex(ReviewLedgerBlocked, "precommit_rejected"):
            self.record()
        self.assertEqual(self.count("sns_media_review_events"), 0)
        self.assertEqual(self.count("sns_media_review_queue_bindings"), 0)

    def test_expected_queue_fingerprint_is_required_for_guarded_record(self):
        without_hash = replace(self.req, expected_queue_sha256=None)
        with self.assertRaisesRegex(ReviewLedgerBlocked, "review_storage_failed"):
            self.record(request=without_hash)
        self.assertEqual(self.count("sns_media_review_events"), 0)
        self.assertEqual(self.count("sns_media_review_queue_reconciliation_events"), 0)

    def test_replay_or_stale_reconciliation_version_is_rejected(self):
        self.record()
        self.guard.reconcile_once(
            key=KEY, source=self.source,
            operation_id="sync_first_0000000000001", expected_binding_version=1,
            as_of=NOW,
        )
        for version, op in (
            (1, "sync_next_00000000000002"),
            (2, "sync_first_0000000000001"),
        ):
            with self.subTest(version=version, op=op), self.assertRaises(
                QueueReconciliationBlocked
            ):
                self.guard.reconcile_once(
                    key=KEY, source=self.source,
                    operation_id=op, expected_binding_version=version, as_of=NOW,
                )
        self.assertEqual(self.count("sns_media_review_queue_reconciliation_events"), 2)

    def test_atomic_rollback_if_queue_binding_write_fails(self):
        self.db.execute(
            """CREATE TRIGGER stop_binding_insert BEFORE INSERT
               ON sns_media_review_queue_reconciliation_events
               BEGIN SELECT RAISE(ABORT,'injected'); END"""
        )
        with self.assertRaisesRegex(ReviewLedgerBlocked, "review_storage_failed"):
            self.record()
        for table in (
            "sns_media_review_heads", "sns_media_review_events",
            "sns_media_review_queue_bindings",
            "sns_media_review_queue_reconciliation_events",
        ):
            self.assertEqual(self.count(table), 0)
        self.assertFalse(self.db.in_transaction)

    def test_revocation_and_binding_are_atomic_even_with_rights_loss(self):
        self.record()
        self.ctx.evidence_by_id[next(iter(self.ctx.evidence_by_id))]["revoked"] = True
        saved = self.revoke()
        self.assertEqual(saved["ledger_version"], 2)
        self.assertFalse(saved["publish_authorized"])
        self.assertEqual(self.guard.barrier(*KEY)["state"], "REVOKED_BLOCKED")
        self.assertEqual(verify_ledger_integrity(self.db, *KEY)["review_state"], "REVOKED")
        self.assertEqual(self.count("sns_media_review_queue_reconciliation_events"), 2)
        with self.assertRaises(QueueReconciliationBlocked):
            self.guard.reconcile_once(
                key=KEY, source=self.source,
                operation_id="sync_after_revocation00001", expected_binding_version=2,
                as_of=NOW,
            )

    def test_revocation_rollback_on_binding_failure_preserves_block(self):
        self.record()
        self.db.execute(
            """CREATE TRIGGER stop_revoke_binding BEFORE INSERT
               ON sns_media_review_queue_reconciliation_events
               WHEN NEW.action='REVIEW_REVOKED'
               BEGIN SELECT RAISE(ABORT,'injected'); END"""
        )
        with self.assertRaisesRegex(ReviewLedgerBlocked, "review_storage_failed"):
            self.revoke()
        self.assertEqual(verify_ledger_integrity(self.db, *KEY)["review_state"], "REVIEW_RECORDED_ONLY")
        self.assertEqual(self.guard.barrier(*KEY)["state"], "REVIEW_RECORDED_BLOCKED")
        self.assertFalse(self.db.in_transaction)

    def test_separate_authority_connection_is_rejected_without_ledger_write(self):
        another = setup_db()
        try:
            with self.assertRaisesRegex(ReviewLedgerBlocked, "queue_authority_database_mismatch"):
                record_review(
                    self.db, self.req, AUTHORIZATION,
                    verifier=self.identity, canonical=self.source, trusted_issuer=ISSUER,
                    operation_id=REVIEW_OPERATION, expected_ledger_version=0,
                    queue_authority=ReviewQueueReconciliation(another), as_of=NOW,
                )
            self.assertEqual(self.count("sns_media_review_events"), 0)
        finally:
            another.close()

    def test_journal_is_append_only_and_tampered_binding_is_detected(self):
        self.record()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE sns_media_review_queue_reconciliation_events SET action='SOURCE_MATCH'",
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM sns_media_review_queue_reconciliation_events")
        self.db.execute(
            "UPDATE sns_media_review_queue_bindings SET queue_sha256=? WHERE queue_id=?",
            ("f" * 64, KEY[2]),
        )
        with self.assertRaisesRegex(QueueReconciliationBlocked, "queue_binding_head_tampered"):
            self.guard.barrier(*KEY)

    def test_two_connections_reject_stale_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "review.db")
            one = setup_db(path)
            two = sqlite3.connect(path, isolation_level=None, timeout=2)
            two.execute("PRAGMA foreign_keys = ON")
            try:
                context = good_context()
                request = replace(
                    good_request(context),
                    expected_queue_sha256=queue_fingerprint(context.queue),
                )
                record_review(
                    one, request, AUTHORIZATION, verifier=FakeIdentityVerifier(),
                    canonical=FakeCanonicalReader(context), trusted_issuer=ISSUER,
                    operation_id=REVIEW_OPERATION, expected_ledger_version=0,
                    queue_authority=ReviewQueueReconciliation(one), as_of=NOW,
                )
                first = ReviewQueueReconciliation(one)
                first.reconcile_once(
                    key=KEY, source=FakeCanonicalReader(context),
                    operation_id="sync_dual_000000000001",
                    expected_binding_version=1, as_of=NOW,
                )
                with self.assertRaisesRegex(QueueReconciliationBlocked, "queue_binding_version_conflict"):
                    ReviewQueueReconciliation(two).reconcile_once(
                        key=KEY, source=FakeCanonicalReader(context),
                        operation_id="sync_dual_000000000002",
                        expected_binding_version=1, as_of=NOW,
                    )
            finally:
                one.close()
                two.close()

    def test_unbound_legacy_revocation_cannot_leave_apparent_valid_binding(self):
        self.record()
        # A remaining legacy ledger call without the optional guard can
        # revoke safely, but its companion binding must not appear in sync.
        revoke_review(
            self.db, self.req, AUTHORIZATION,
            verifier=self.identity, trusted_issuer=ISSUER,
            operation_id="op_legacy_revoke_00000001",
            expected_ledger_version=1, reason_code="consent_withdrawn",
            as_of=NOW,
        )
        before = self.guard.barrier(*KEY)
        self.assertEqual(before["state"], "LEDGER_DIVERGENCE_BLOCKED")
        self.assertFalse(before["publish_authorized"])
        conflict = self.guard.reconcile_once(
            key=KEY, source=self.source,
            operation_id="sync_legacy_divergence00001",
            expected_binding_version=1, as_of=NOW,
        )
        self.assertTrue(conflict["quarantined"])
        self.assertEqual(self.guard.barrier(*KEY)["state"], "LEDGER_DIVERGENCE_BLOCKED")

    def test_reconciliation_has_no_sheets_or_publisher_mutation_dependency(self):
        source = (ROOT / "scripts/media_review_queue_reconciliation.py").read_text()
        for import_line in ("import gspread", "from src.sheets_client",
                            "from publishers", "update_queue_item(", "publish("):
            self.assertNotIn(import_line, source)


if __name__ == "__main__":
    unittest.main()
