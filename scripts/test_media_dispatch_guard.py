#!/usr/bin/env python3
"""Offline 5B-6C: review+intent+dispatch concurrency, rights, no-post invariants."""
from __future__ import annotations

import copy
import sqlite3
import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_dispatch_guard import (  # noqa: E402
    DispatchBlocked, MediaDispatchGuard, initialize_dispatch_schema,
)
from media_review_canonical_adapter import CanonicalProtectedReviewReader  # noqa: E402
from media_review_protected_evidence import ProtectedEvidenceVault  # noqa: E402
from media_review_transactional_ledger import revoke_review  # noqa: E402
import test_media_publish_intent_authority as fixtures  # noqa: E402

KEY, NOW, ISSUER = fixtures.KEY, fixtures.NOW, fixtures.ISSUER

STAGE_OP = "dispatch_stage_20261012_000001"


class MediaDispatchGuardTests(fixtures.PublishIntentTests):
    """Re-run prior 22 intent tests plus new dispatch-focused tests."""

    def setUp(self):
        super().setUp()
        initialize_dispatch_schema(self.db)
        self.dispatch = MediaDispatchGuard(self.db)

    def ready(self):
        self.review_and_match()
        self.reserve()

    def stage(self, **kw):
        defaults = {
            "key": KEY, "operation_id": STAGE_OP,
            "expected_intent_version": 1,
            "verifier": self.verifier, "bearer": self.bearer,
            "trusted_issuer": ISSUER, "source": self.canonical, "as_of": NOW,
        }
        defaults.update(kw)
        return self.dispatch.stage(**defaults)

    def finalize(self, action="RECHECK", **kw):
        defaults = {
            "key": KEY, "operation_id": "dispatch_recheck_20261012_00001",
            "expected_dispatch_version": 1,
            "verifier": self.verifier, "bearer": self.bearer,
            "trusted_issuer": ISSUER, "source": self.canonical, "as_of": NOW,
            "action": action,
        }
        defaults.update(kw)
        return self.dispatch.finalize_blocked(**defaults)

    def test_dispatch_migration_needs_intent_schema(self):
        db = sqlite3.connect(":memory:", isolation_level=None)
        try:
            with self.assertRaisesRegex(DispatchBlocked, "dispatch_intent_migration_required"):
                initialize_dispatch_schema(db)
        finally:
            db.close()

    def test_dispatch_no_review_or_no_intent_is_denied(self):
        self.assertEqual(self.dispatch.inspect(key=KEY)["status"], "NO_DISPATCH")
        with self.assertRaises(DispatchBlocked):
            self.stage()
        self.assertEqual(self.count("sns_media_dispatch_events"), 0)

    def test_dispatch_intent_holding_required_and_full_chain_checked(self):
        self.ready()
        snapshot = copy.deepcopy(self.context)
        stage = self.stage()
        self.assertEqual(stage["status"], "STAGED_BLOCKED")
        self.assertIs(stage["publish_authorized"], False)
        self.assertIs(stage["dispatch_allowed"], False)
        self.assertIs(stage["publish_attempted"], False)
        self.assertEqual(self.dispatch.inspect(key=KEY)["status"], "STAGED_BLOCKED")
        self.assertEqual(self.count("sns_media_dispatch_events"), 1)
        self.assertEqual(self.context, snapshot)
        payload = self.db.execute(
            "SELECT payload_json FROM sns_media_dispatch_events",
        ).fetchone()[0]
        for secret in (self.jwt, self.bearer, "PRIVATE_POST_BODY",
                       "private_original_evidence", "https://secret.example"):
            self.assertNotIn(secret, payload)

    def test_replay_second_stage_and_stale_intent_blocked(self):
        self.ready()
        self.stage()
        for operation, version in (
            (STAGE_OP, 1), ("dispatch_second_stage_20261012_001", 1),
            ("dispatch_stale_stage_20261012_002", 2),
        ):
            with self.subTest(operation=operation), self.assertRaises(DispatchBlocked):
                self.stage(operation_id=operation, expected_intent_version=version)
        self.assertEqual(self.count("sns_media_dispatch_events"), 1)

    def test_source_drift_before_stage_blocks_without_any_head(self):
        self.ready()
        self.context.queue["public_post_text"] = "edited after reservation"
        with self.assertRaises(DispatchBlocked):
            self.stage()
        self.assertEqual(self.count("sns_media_dispatch_heads"), 0)

    def test_review_revocation_before_stage_blocks(self):
        self.ready()
        revoke_review(
            self.db, self.review, self.bearer,
            verifier=self.verifier, trusted_issuer=ISSUER,
            operation_id="op_dispatch_revoke_review_0001",
            expected_ledger_version=1, reason_code="consent_withdrawn",
            queue_authority=self.guard, as_of=NOW,
        )
        with self.assertRaises(DispatchBlocked):
            self.stage()
        self.assertEqual(self.count("sns_media_dispatch_events"), 0)

    def test_proof_expired_before_stage_blocks(self):
        self.ready()
        with self.assertRaises(DispatchBlocked):
            self.stage(as_of=NOW + timedelta(hours=26))
        self.assertEqual(self.count("sns_media_dispatch_heads"), 0)

    def test_unconfigured_source_or_auth_denies_before_staging(self):
        self.ready()
        for args in (
            {"source": None}, {"verifier": None},
            {"bearer": "Bearer tampered"},
            {"trusted_issuer": "https://wrong.example"},
        ):
            with self.subTest(args=list(args)), self.assertRaises(DispatchBlocked):
                self.stage(**args)
        self.assertEqual(self.count("sns_media_dispatch_heads"), 0)

    def test_stale_binding_version_mismatch_denied(self):
        self.ready()
        with self.assertRaises(DispatchBlocked):
            self.stage(expected_intent_version=999)
        self.assertEqual(self.count("sns_media_dispatch_events"), 0)

    def test_recheck_unchanged_does_not_append_event(self):
        self.ready()
        self.stage()
        result = self.finalize()
        self.assertEqual(result["status"], "STAGED_BLOCKED")
        self.assertFalse(result["dispatch_allowed"])
        self.assertEqual(self.count("sns_media_dispatch_events"), 1)

    def test_recheck_queue_drift_quarantines_without_reuse(self):
        self.ready()
        self.stage()
        self.context.queue["public_post_text"] += " changed"
        first = self.finalize()
        self.assertEqual(first["status"], "DRIFT_BLOCKED")
        self.assertEqual(self.dispatch.inspect(key=KEY)["dispatch_version"], 2)
        with self.assertRaises(DispatchBlocked):
            self.finalize(operation_id="dispatch_recheck_replayed_20261012_02",
                          expected_dispatch_version=2)

    def test_recheck_revocation_or_rights_loss_quarantines(self):
        self.ready()
        self.stage()
        eid = next(iter(self.context.evidence_by_id))
        self.vault.revoke(
            evidence_id=eid, bearer_token=self.bearer,
            verifier=self.verifier, trusted_issuer=ISSUER,
            operation_id="evop_dispatch_rights_revoke_00001",
            expected_revision=1, as_of=NOW,
        )
        self.assertEqual(self.finalize()["status"], "DRIFT_BLOCKED")

    def test_recheck_source_outage_quarantines(self):
        self.ready()
        self.stage()
        self.source_fixture.offline = True
        self.assertEqual(self.finalize()["status"], "DRIFT_BLOCKED")

    def test_recheck_stage_expiry_quarantines(self):
        self.ready()
        self.stage()
        self.assertEqual(
            self.finalize(as_of=NOW + timedelta(minutes=2))["status"],
            "DRIFT_BLOCKED",
        )

    def test_operator_can_cancel_after_source_goes_offline(self):
        self.ready()
        self.stage()
        self.source_fixture.offline = True
        result = self.finalize(
            action="CANCEL",
            operation_id="dispatch_cancel_20261012_000001",
            source=None,
        )
        self.assertEqual(result["status"], "CANCELLED_BLOCKED")
        self.assertFalse(result["publish_authorized"])
        with self.assertRaises(DispatchBlocked):
            self.stage(operation_id="dispatch_second_20261012_00003")

    def test_uncertain_outcome_mark_is_terminal_and_prevents_retry(self):
        self.ready()
        self.stage()
        first = self.finalize(
            action="MARK_UNCERTAIN",
            operation_id="dispatch_mark_uncertain_20261012_01",
            source=None,
        )
        self.assertEqual(first["status"], "OUTCOME_UNCERTAIN_BLOCKED")
        self.assertIs(first["dispatch_allowed"], False)
        with self.assertRaises(DispatchBlocked):
            self.finalize(
                expected_dispatch_version=2,
                operation_id="dispatch_unverified_again_20261012_02",
            )
        self.assertEqual(self.count("sns_media_dispatch_events"), 2)

    def test_rollback_on_fault_injected_event_insert(self):
        self.ready()
        self.db.execute(
            """CREATE TRIGGER reject_stage BEFORE INSERT
               ON sns_media_dispatch_events
               BEGIN SELECT RAISE(ABORT,'injected_failure'); END""",
        )
        with self.assertRaises(DispatchBlocked):
            self.stage()
        self.assertEqual(self.count("sns_media_dispatch_heads"), 0)
        self.assertFalse(self.db.in_transaction)

    def test_append_only_and_tampered_heads_detected(self):
        self.ready()
        self.stage()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE sns_media_dispatch_events SET action='CANCEL'",
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM sns_media_dispatch_events")
        self.db.execute(
            "UPDATE sns_media_dispatch_heads SET source_id=? WHERE queue_id=?",
            ("altered_source", KEY[2]),
        )
        with self.assertRaisesRegex(DispatchBlocked, "dispatch_head_tampered"):
            self.dispatch.inspect(key=KEY)

    def test_two_sqlite_connections_share_one_unique_dispatch_record(self):
        self.ready()
        self.stage()
        another = sqlite3.connect(self.path, isolation_level=None, timeout=2)
        another.execute("PRAGMA foreign_keys=ON")
        try:
            guard = MediaDispatchGuard(another)
            source = CanonicalProtectedReviewReader(
                source=fixtures.Snapshots(self.context), vault=ProtectedEvidenceVault(another),
            )
            with self.assertRaises(DispatchBlocked):
                guard.stage(
                    key=KEY, operation_id="dispatch_second_connection_00001",
                    expected_intent_version=1,
                    verifier=self.make_verifier(another), bearer=self.bearer,
                    trusted_issuer=ISSUER, source=source, as_of=NOW,
                )
            self.assertEqual(self.count("sns_media_dispatch_events"), 1)
        finally:
            another.close()

    def test_no_transport_server_or_publisher_dependencies(self):
        text = (ROOT / "scripts" / "media_dispatch_guard.py").read_text()
        for forbidden in (
            "requests.post(", "import gspread", "SheetsClient(",
            "PUBLISH_ENABLED", "ALLOW_MEDIA_POSTS", "_publish_container(",
        ):
            self.assertNotIn(forbidden, text)
        self.assertFalse(self.dispatch.inspect(key=KEY)["publish_authorized"])


if __name__ == "__main__":
    unittest.main()
