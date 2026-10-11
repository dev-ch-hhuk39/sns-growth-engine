#!/usr/bin/env python3
"""Offline atomicity, integrity and no-publish tests for Phase 5B-5A."""
from __future__ import annotations

import copy
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_review_transactional_ledger import (  # noqa: E402
    ReviewLedgerBlocked, initialize_review_schema, record_review,
    revoke_review, verify_ledger_integrity,
)
from test_media_review_trusted_precommit import (  # noqa: E402
    AUTHORIZATION, ISSUER, NOW, FakeCanonicalReader, FakeIdentityVerifier,
    good_context, good_request,
)

FIRST_OP = "op_review_00000000000001"
SECOND_OP = "op_review_00000000000002"
REVOKE_OP = "op_revoke_00000000000001"
KEY = ("liver_manager", "lm_1800_clip_media", "clip_001")


def new_db(path: str = ":memory:") -> sqlite3.Connection:
    db = sqlite3.connect(path, isolation_level=None, timeout=2.0)
    initialize_review_schema(db)
    return db


def submit(db, *, request=None, context=None, operation_id=FIRST_OP,
           expected_ledger_version=0, verifier=None, reader=None, as_of=NOW):
    context = context or good_context()
    return record_review(
        db, request or good_request(context), AUTHORIZATION,
        verifier=verifier or FakeIdentityVerifier(),
        canonical=reader or FakeCanonicalReader(context),
        trusted_issuer=ISSUER, operation_id=operation_id,
        expected_ledger_version=expected_ledger_version, as_of=as_of,
    )


def revoke(db, *, request=None, operation_id=REVOKE_OP,
           expected_ledger_version=1, reason_code="consent_withdrawn",
           verifier=None, as_of=NOW):
    return revoke_review(
        db, request or good_request(), AUTHORIZATION,
        verifier=verifier or FakeIdentityVerifier(),
        trusted_issuer=ISSUER,
        operation_id=operation_id,
        expected_ledger_version=expected_ledger_version,
        reason_code=reason_code, as_of=as_of,
    )


def rows(db):
    return (
        db.execute("SELECT COUNT(*) FROM sns_media_review_events").fetchone()[0],
        db.execute("SELECT COUNT(*) FROM sns_media_review_heads").fetchone()[0],
    )


class TransactionalReviewLedgerTests(unittest.TestCase):
    def setUp(self):
        self.db = new_db()

    def tearDown(self):
        self.db.close()

    def test_successful_precommit_only_records_isolated_review(self):
        context = good_context()
        expected_context = copy.deepcopy(context)
        saved = submit(self.db, context=context)
        self.assertEqual(saved["status"], "ISOLATED_REVIEW_LEDGER_RECORDED_NOT_AUTHORIZED")
        self.assertEqual(saved["ledger_version"], 1)
        self.assertEqual(saved["action"], "REVIEW_RECORD")
        self.assertTrue(saved["review_record_persisted"])
        self.assertIs(saved["authenticated_approval_integrated"], False)
        self.assertIs(saved["external_queue_atomicity_guaranteed"], False)
        self.assertIs(saved["requires_authoritative_queue_reconciliation"], True)
        for flag in ("effective_approval", "ready_transitions_performed", "publish_authorized"):
            self.assertIs(saved[flag], False)
        self.assertEqual(context, expected_context)
        self.assertEqual(rows(self.db), (1, 1))
        self.assertEqual(verify_ledger_integrity(self.db, *KEY)["review_state"], "REVIEW_RECORDED_ONLY")
        payload = self.db.execute("SELECT payload_json FROM sns_media_review_events").fetchone()[0]
        for forbidden in (AUTHORIZATION, "SENSITIVE_EVIDENCE", "PRIVATE_POST_BODY",
                          "raw_evidence_text", "media_url"):
            self.assertNotIn(forbidden, payload)

    def test_absent_identity_or_canonical_backend_never_writes(self):
        ctx = good_context()
        for verifier, canonical in (
            (None, FakeCanonicalReader(ctx)),
            (FakeIdentityVerifier(), None),
        ):
            with self.subTest(verifier=verifier is None), self.assertRaisesRegex(
                ReviewLedgerBlocked, "precommit_rejected"
            ):
                record_review(
                    self.db, good_request(ctx), AUTHORIZATION,
                    verifier=verifier, canonical=canonical, trusted_issuer=ISSUER,
                    operation_id=FIRST_OP, expected_ledger_version=0, as_of=NOW,
                )
        self.assertEqual(rows(self.db), (0, 0))

    def test_invalid_expired_evidence_or_queue_revision_fails_with_rollback(self):
        for change in (
            {"rights_status": "DENIED"},
            {"permission_status": "UNKNOWN"},
            {"revision": "rev_new_version"},
            {"media_asset_id": ""},
        ):
            ctx = good_context()
            ctx.queue.update(change)
            with self.subTest(change=change), self.assertRaisesRegex(
                ReviewLedgerBlocked, "precommit_rejected"
            ):
                submit(self.db, context=ctx)
            self.assertEqual(rows(self.db), (0, 0))
        ctx = good_context()
        ctx.evidence_by_id[next(iter(ctx.evidence_by_id))]["revoked"] = True
        with self.assertRaisesRegex(ReviewLedgerBlocked, "precommit_rejected"):
            submit(self.db, context=ctx)
        self.assertEqual(rows(self.db), (0, 0))

    def test_replay_old_version_and_second_approval_do_not_append(self):
        submit(self.db)
        with self.assertRaisesRegex(ReviewLedgerBlocked, "operation_replayed"):
            submit(self.db)
        with self.assertRaisesRegex(ReviewLedgerBlocked, "review_version_conflict"):
            submit(self.db, operation_id=SECOND_OP, expected_ledger_version=0)
        with self.assertRaisesRegex(ReviewLedgerBlocked, "review_already_recorded"):
            submit(self.db, operation_id=SECOND_OP, expected_ledger_version=1)
        self.assertEqual(rows(self.db), (1, 1))

    def test_revocation_can_be_authorized_even_after_rights_disappear(self):
        submit(self.db)
        old = verify_ledger_integrity(self.db, *KEY)["head_sha256"]
        result = revoke(self.db, reason_code="consent_withdrawn")
        self.assertEqual(result["action"], "REVOKE")
        self.assertEqual(result["ledger_version"], 2)
        self.assertFalse(result["publish_authorized"])
        self.assertEqual(rows(self.db), (2, 1))
        integrity = verify_ledger_integrity(self.db, *KEY)
        self.assertEqual(integrity["review_state"], "REVOKED")
        self.assertNotEqual(integrity["head_sha256"], old)
        events = self.db.execute(
            "SELECT previous_event_sha256,event_sha256 FROM sns_media_review_events ORDER BY sequence"
        ).fetchall()
        self.assertEqual(events[1][0], events[0][1])

    def test_revoke_requires_role_account_mfa_and_reason(self):
        submit(self.db)
        for reason in ("", "published", "delete_everything"):
            with self.assertRaisesRegex(ReviewLedgerBlocked, "revocation_reason_invalid"):
                revoke(self.db, reason_code=reason)
        principal = FakeIdentityVerifier()
        principal.principal = replace(principal.principal, account_scopes=frozenset({"night_scout"}))
        with self.assertRaisesRegex(ReviewLedgerBlocked, "revocation_authentication_failed"):
            revoke(self.db, verifier=principal)
        self.assertEqual(rows(self.db), (1, 1))

    def test_revoking_nonexistent_or_already_revoked_is_rejected(self):
        with self.assertRaisesRegex(ReviewLedgerBlocked, "no_active_record_to_revoke"):
            revoke(self.db, expected_ledger_version=0)
        self.assertEqual(rows(self.db), (0, 0))
        submit(self.db)
        revoke(self.db)
        with self.assertRaisesRegex(ReviewLedgerBlocked, "no_active_record_to_revoke"):
            revoke(self.db, operation_id=SECOND_OP, expected_ledger_version=2)

    def test_revocation_requires_exact_previous_review_fingerprint(self):
        submit(self.db)
        changed = replace(good_request(), expected_queue_revision="rev_9999999")
        with self.assertRaisesRegex(ReviewLedgerBlocked, "revocation_target_changed"):
            revoke(self.db, request=changed)
        self.assertEqual(rows(self.db), (1, 1))

    def test_same_draft_cannot_be_reapproved_after_revocation(self):
        submit(self.db)
        revoke(self.db)
        with self.assertRaisesRegex(ReviewLedgerBlocked, "revoked_draft_cannot_be_reused"):
            submit(self.db, operation_id=SECOND_OP, expected_ledger_version=2)
        self.assertEqual(rows(self.db), (2, 1))

    def test_database_failure_rolls_back_event_and_head_in_same_transaction(self):
        self.db.execute("""
            CREATE TRIGGER test_inject_head_update_failure
            BEFORE UPDATE ON sns_media_review_heads
            BEGIN SELECT RAISE(ABORT, 'PRIVATE_DATABASE_ERROR'); END
        """)
        with self.assertRaisesRegex(ReviewLedgerBlocked, "review_storage_failed") as caught:
            submit(self.db)
        self.assertNotIn("PRIVATE_DATABASE_ERROR", str(caught.exception))
        self.assertEqual(rows(self.db), (0, 0))
        self.db.execute("DROP TRIGGER test_inject_head_update_failure")
        submit(self.db)
        self.assertEqual(rows(self.db), (1, 1))

    def test_immutable_event_triggers_block_update_and_delete(self):
        submit(self.db)
        for statement in (
            "UPDATE sns_media_review_events SET action='REVOKE'",
            "DELETE FROM sns_media_review_events",
            "DELETE FROM sns_media_review_heads",
        ):
            with self.subTest(statement=statement), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute(statement)
        self.assertEqual(rows(self.db), (1, 1))

    def test_chain_detects_mutated_head_version_and_state(self):
        submit(self.db)
        self.db.execute(
            "UPDATE sns_media_review_heads SET last_event_sha256=? WHERE queue_id=?",
            ("f" * 64, "clip_001"),
        )
        with self.assertRaisesRegex(ReviewLedgerBlocked, "review_history_head_invalid"):
            verify_ledger_integrity(self.db, *KEY)

    def test_chain_detects_tampered_draft_binding_and_queue_revision(self):
        for field, replacement in (
            ("last_draft_event_sha256", "f" * 64),
            ("last_queue_revision", "rev_unauthorized"),
        ):
            with self.subTest(field=field):
                db = new_db()
                try:
                    submit(db)
                    db.execute(
                        "UPDATE sns_media_review_heads SET " + field + "=? WHERE queue_id=?",
                        (replacement, "clip_001"),
                    )
                    with self.assertRaisesRegex(
                        ReviewLedgerBlocked, "review_history_head_invalid"
                    ):
                        verify_ledger_integrity(db, *KEY)
                finally:
                    db.close()

    def test_review_ledger_requires_foreign_key_integrity_and_schema(self):
        no_fks = sqlite3.connect(":memory:", isolation_level=None)
        try:
            no_fks.executescript((ROOT / "db/migrations/0001_sns_media_review_ledger.sql").read_text())
            no_fks.execute("PRAGMA foreign_keys=OFF")
            with self.assertRaisesRegex(ReviewLedgerBlocked, "review_database_unavailable"):
                submit(no_fks)
        finally:
            no_fks.close()

    def test_rejects_malformed_operation_and_boolean_version(self):
        for op, version in (("", 0), ("op_short", 0), (FIRST_OP, True), (FIRST_OP, -1)):
            with self.subTest(op=op, version=version), self.assertRaisesRegex(
                ReviewLedgerBlocked, "operation_identity_invalid"
            ):
                submit(self.db, operation_id=op, expected_ledger_version=version)
        self.assertEqual(rows(self.db), (0, 0))

    def test_file_backed_second_connection_observes_cas_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            path = str(Path(temp) / "review.db")
            c1 = new_db(path)
            c2 = sqlite3.connect(path, isolation_level=None, timeout=2)
            c2.execute("PRAGMA foreign_keys=ON")
            try:
                submit(c1)
                with self.assertRaisesRegex(ReviewLedgerBlocked, "review_version_conflict"):
                    submit(c2, operation_id=SECOND_OP, expected_ledger_version=0)
                self.assertEqual(rows(c1), (1, 1))
                self.assertEqual(rows(c2), (1, 1))
            finally:
                c2.close()
                c1.close()

    def test_no_sheets_or_publisher_imports_in_ledger(self):
        text = (ROOT / "scripts/media_review_transactional_ledger.py").read_text()
        for forbidden in ("from sheets_client", "SheetsClient(", "update_queue_item(",
                          "ThreadsPublisher", "save_posted_result(", "FastAPI("):
            self.assertNotIn(forbidden, text)
        sql = (ROOT / "db/migrations/0001_sns_media_review_ledger.sql").read_text()
        self.assertIn("event_no_update", sql)
        self.assertIn("event_no_delete", sql)


if __name__ == "__main__":
    unittest.main()
