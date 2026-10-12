#!/usr/bin/env python3
"""Phase 5B-6E synthetic RS256 reviewer -> shadow queue -> intent -> dispatch.

Never accesses live Google Sheets, IdP, API, credentials or production data.
"""
from __future__ import annotations

import copy
import sqlite3
import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_shadow_queue_authority import (  # noqa: E402
    MediaShadowQueueAuthority, ShadowQueueBlocked,
    SQLiteShadowOperationalSnapshot, initialize_shadow_queue_schema,
    MAX_SNAPSHOT_BYTES, ZERO,
)
from media_dispatch_guard import MediaDispatchGuard, initialize_dispatch_schema  # noqa: E402
from media_review_canonical_adapter import CanonicalProtectedReviewReader  # noqa: E402
from media_review_protected_evidence import ProtectedEvidenceVault  # noqa: E402
from media_review_trusted_precommit import PrecommitBlocked  # noqa: E402
from media_review_transactional_ledger import ReviewLedgerBlocked  # noqa: E402
from media_review_queue_reconciliation import QueueReconciliationBlocked  # noqa: E402
import test_media_publish_intent_authority as fixtures  # noqa: E402

KEY, NOW, ISSUER = fixtures.KEY, fixtures.NOW, fixtures.ISSUER

FIRST = "shadow_import_20261012_000001"


class ShadowQueueAuthorityTests(fixtures.PublishIntentTests):
    """Re-run 22 trusted-intent tests and add shadow authority tests."""

    def setUp(self):
        super().setUp()
        initialize_dispatch_schema(self.db)
        initialize_shadow_queue_schema(self.db)
        self.shadow = MediaShadowQueueAuthority(self.db)
        self.external = self.canonical
        self.read_clock = NOW

    def capture(self, operation=FIRST, **changes):
        args = {
            "key": KEY, "operation_id": operation, "expected_version": 0,
            "expected_head_sha256": ZERO,
            "verifier": self.verifier, "bearer": self.bearer,
            "trusted_issuer": ISSUER, "source": self.external,
            "as_of": NOW,
        }
        args.update(changes)
        return self.shadow.capture(**args)

    def observe(self, *, version, sha, operation="shadow_observe_20261012_000001",
                **changes):
        args = {
            "key": KEY, "operation_id": operation,
            "expected_version": version, "expected_head_sha256": sha,
            "verifier": self.verifier, "bearer": self.bearer,
            "trusted_issuer": ISSUER, "source": self.external,
            "as_of": NOW,
        }
        args.update(changes)
        return self.shadow.observe(**args)

    def local(self, db=None, vault=None, clock=None):
        db = db or self.db
        vault = vault or self.vault
        clock = clock or (lambda: self.read_clock)
        return CanonicalProtectedReviewReader(
            source=SQLiteShadowOperationalSnapshot(
                db=db, vault=vault, clock=clock,
            ), vault=vault,
        )

    def test_migration_requires_prior_schemas(self):
        db = sqlite3.connect(":memory:", isolation_level=None)
        try:
            with self.assertRaisesRegex(ShadowQueueBlocked, "shadow_prerequisite_migration_missing"):
                initialize_shadow_queue_schema(db)
        finally:
            db.close()

    def test_shadow_import_authenticated_and_non_authorizing(self):
        original = copy.deepcopy(self.context)
        result = self.capture()
        self.assertEqual(result["status"], "SHADOW_BLOCKED")
        self.assertEqual(result["shadow_version"], 1)
        self.assertFalse(result["effective_approval"])
        self.assertFalse(result["publish_authorized"])
        self.assertFalse(result["dispatch_allowed"])
        self.assertFalse(result["external_queue_atomicity_guaranteed"])
        self.assertEqual(self.count("sns_media_shadow_queue_events"), 1)
        self.assertEqual(self.count("sns_media_shadow_queue_heads"), 1)
        self.assertEqual(self.context, original)
        self.assertEqual(self.local().load_current(*KEY).queue, self.context.queue)
        info = self.shadow.inspect(key=KEY)
        for token in ("PRIVATE_POST_BODY", self.jwt, "private_original_evidence"):
            self.assertNotIn(token, str(result))
            self.assertNotIn(token, str(info))
            self.assertNotIn(
                token,
                self.db.execute(
                    "SELECT payload_json FROM sns_media_shadow_queue_events",
                ).fetchone()[0],
            )

    def test_signed_session_and_role_required(self):
        for overrides in (
            {"bearer": "Bearer invalid"},
            {"bearer": "Bearer " + self.token({"aud": "invalid"})},
            {"verifier": None},
            {"source": None},
            {"trusted_issuer": "https://fake-issuer.invalid"},
        ):
            with self.subTest(override=list(overrides)), self.assertRaises(ShadowQueueBlocked):
                self.capture(**overrides)
        self.assertEqual(self.count("sns_media_shadow_queue_events"), 0)

    def test_cross_account_and_invalid_queue_id_rejected(self):
        for candidate in (
            ("night_scout", KEY[1], KEY[2]),
            (KEY[0], "lm_1600_direct_media", KEY[2]),
            (KEY[0], KEY[1], "../wrong"),
        ):
            with self.subTest(candidate=candidate), self.assertRaises(
                (ShadowQueueBlocked, QueueReconciliationBlocked),
            ):
                self.capture(key=candidate)
        self.assertFalse(self.count("sns_media_shadow_queue_heads"))

    def test_bad_evidence_and_rights_cannot_enter_shadow(self):
        eid = next(iter(self.context.evidence_by_id))
        self.vault.revoke(
            evidence_id=eid, bearer_token=self.bearer,
            verifier=self.verifier, trusted_issuer=ISSUER,
            operation_id="evop_shadow_revoke_before_0001",
            expected_revision=1, as_of=NOW,
        )
        with self.assertRaises(ShadowQueueBlocked):
            self.capture()
        self.assertFalse(self.count("sns_media_shadow_queue_events"))

    def test_missing_source_or_untrusted_sensitive_data_is_denied(self):
        self.source_fixture.offline = True
        with self.assertRaises(ShadowQueueBlocked):
            self.capture()
        self.source_fixture.offline = False
        self.context.queue["access_token"] = "fake-token-not-real"
        with self.assertRaises(ShadowQueueBlocked):
            self.capture()
        self.context.queue.pop("access_token")
        self.context.queue["notes"] = "Bearer abcdefghijklmnop"
        with self.assertRaises(ShadowQueueBlocked):
            self.capture()
        self.assertEqual(self.count("sns_media_shadow_queue_heads"), 0)

    def test_oversized_snapshot_rejected_without_any_write(self):
        self.context.queue["filler"] = "x" * (MAX_SNAPSHOT_BYTES + 100)
        with self.assertRaises(ShadowQueueBlocked):
            self.capture()
        self.assertEqual(self.count("sns_media_shadow_queue_heads"), 0)

    def test_local_read_limited_to_recent_observations(self):
        self.capture()
        self.read_clock = NOW + timedelta(seconds=91)
        with self.assertRaises(PrecommitBlocked):
            self.local().load_current(*KEY)
        self.read_clock = NOW + timedelta(seconds=15)
        self.assertEqual(self.local().load_current(*KEY).queue, self.context.queue)

    def test_read_from_same_sqlite_transaction(self):
        self.capture()
        internal = self.local()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            context = internal.load_current(*KEY)
            self.assertEqual(context.queue["media_asset_id"],
                             self.context.queue["media_asset_id"])
            self.assertTrue(self.db.in_transaction)
        finally:
            self.db.rollback()

    def test_disabled_reviewer_grant_blocks_new_import(self):
        self.db.execute(
            "UPDATE sns_review_account_grants SET enabled=0 WHERE subject=?",
            (fixtures.SUBJECT,),
        )
        with self.assertRaises(ShadowQueueBlocked):
            self.capture()
        self.assertEqual(self.count("sns_media_shadow_queue_heads"), 0)

    def test_expired_shadow_cannot_support_new_review(self):
        from media_review_transactional_ledger import record_review
        self.capture()
        self.canonical = self.local(
            clock=lambda: NOW + timedelta(seconds=91),
        )
        with self.assertRaises(ReviewLedgerBlocked):
            record_review(
                self.db, self.review, self.bearer,
                verifier=self.verifier, canonical=self.canonical,
                trusted_issuer=ISSUER,
                operation_id="op_shadow_stale_review_20261012_01",
                expected_ledger_version=0, queue_authority=self.guard,
                as_of=NOW,
            )
        self.assertEqual(self.count("sns_media_review_events"), 0)
        self.assertFalse(self.db.in_transaction)

    def test_import_refetch_uses_exact_one_snapshot(self):
        class OnceOnly(fixtures.Snapshots):
            def __init__(self, context):
                super().__init__(context)
                self.calls = 0
            def load(self, *args):
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("source reread would race")
                return super().load(*args)
        fake = OnceOnly(self.context)
        self.external = CanonicalProtectedReviewReader(source=fake, vault=self.vault)
        self.capture()
        self.assertEqual(fake.calls, 1)

    def test_refresh_only_before_any_review(self):
        created = self.capture()
        self.context.queue["public_post_text"] = "edited before first review"
        later = self.capture(
            operation="shadow_refresh_20261012_000002",
            expected_version=1,
            expected_head_sha256=created["shadow_event_sha256"],
        )
        self.assertEqual(later["shadow_version"], 2)
        self.assertEqual(
            self.local().load_current(*KEY).queue["public_post_text"],
            "edited before first review",
        )
        self.assertEqual(self.count("sns_media_shadow_queue_events"), 2)

    def test_refresh_version_and_head_digest_cas(self):
        first = self.capture()
        for kw in (
            {"expected_version": 1, "expected_head_sha256": ZERO},
            {"expected_version": 0, "expected_head_sha256": first["shadow_event_sha256"]},
            {"expected_version": 2, "expected_head_sha256": first["shadow_event_sha256"]},
        ):
            with self.subTest(kw=kw), self.assertRaises(ShadowQueueBlocked):
                self.capture(operation="shadow_invalid_refresh_20261012_01", **kw)
        self.assertEqual(self.count("sns_media_shadow_queue_events"), 1)

    def test_import_replay_is_denied(self):
        self.capture()
        with self.assertRaises(ShadowQueueBlocked):
            self.capture()
        self.assertEqual(self.count("sns_media_shadow_queue_events"), 1)

    def test_internal_sqlite_read_supports_review_intent_and_dispatch(self):
        self.capture()
        # Switch the entire downstream chain to a single immutable SQLite
        # source; the old external provider is no longer read after import.
        self.canonical = self.local()
        self.source_fixture.offline = True
        self.review_and_match()
        held = self.reserve()
        self.assertEqual(held["status"], "HELD_BLOCKED")
        dispatcher = MediaDispatchGuard(self.db)
        stage = dispatcher.stage(
            key=KEY, operation_id="dispatch_shadow_20261012_000001",
            expected_intent_version=1,
            verifier=self.verifier, bearer=self.bearer, trusted_issuer=ISSUER,
            source=self.canonical, as_of=NOW,
        )
        self.assertEqual(stage["status"], "STAGED_BLOCKED")
        self.assertFalse(stage["publish_authorized"])
        self.assertFalse(stage["dispatch_allowed"])
        self.assertFalse(stage["publish_attempted"])
        self.assertEqual(self.count("sns_media_dispatch_events"), 1)

    def test_post_review_refresh_forbidden_but_matching_observation_allowed(self):
        initial = self.capture()
        self.canonical = self.local()
        self.review_and_match()
        with self.assertRaises(ShadowQueueBlocked):
            self.capture(
                operation="shadow_frozen_refresh_20261012_00001",
                expected_version=1,
                expected_head_sha256=initial["shadow_event_sha256"],
            )
        renew = self.observe(
            version=1, sha=initial["shadow_event_sha256"],
        )
        self.assertEqual(renew["status"], "SHADOW_BLOCKED")
        self.assertEqual(renew["shadow_version"], 2)
        self.assertEqual(self.count("sns_media_shadow_queue_events"), 2)
        self.assertEqual(self.count("sns_media_review_events"), 1)

    def test_observed_drift_quarantines_and_cannot_be_read(self):
        first = self.capture()
        self.context.queue["public_post_text"] = "edits outside frozen database"
        result = self.observe(version=1, sha=first["shadow_event_sha256"])
        self.assertEqual(result["status"], "CONFLICT_BLOCKED")
        with self.assertRaises(PrecommitBlocked):
            self.local().load_current(*KEY)
        with self.assertRaises(ShadowQueueBlocked):
            self.capture(
                operation="shadow_post_drift_refresh_20261012_01",
                expected_version=2,
                expected_head_sha256=result["shadow_event_sha256"],
            )
        self.assertEqual(self.count("sns_media_shadow_queue_events"), 2)

    def test_proof_revoked_before_observation_quarantines(self):
        first = self.capture()
        eid = next(iter(self.context.evidence_by_id))
        self.vault.revoke(
            evidence_id=eid, bearer_token=self.bearer,
            verifier=self.verifier, trusted_issuer=ISSUER,
            operation_id="evop_shadow_post_revoke_00001",
            expected_revision=1, as_of=NOW,
        )
        with self.assertRaises(PrecommitBlocked):
            self.local().load_current(*KEY)
        result = self.observe(
            version=1, sha=first["shadow_event_sha256"],
        )
        self.assertEqual(result["status"], "SOURCE_UNAVAILABLE_BLOCKED")

    def test_source_outage_quarantines_without_storing_exception(self):
        first = self.capture()
        self.source_fixture.offline = True
        result = self.observe(version=1, sha=first["shadow_event_sha256"])
        self.assertEqual(result["status"], "SOURCE_UNAVAILABLE_BLOCKED")
        events = [
            row[0] for row in self.db.execute(
                "SELECT payload_json FROM sns_media_shadow_queue_events",
            ).fetchall()
        ]
        self.assertNotIn("never-store-token", str(events))
        self.assertEqual(self.shadow.inspect(key=KEY)["status"], "SOURCE_UNAVAILABLE_BLOCKED")

    def test_repeated_observation_renews_lease_without_content_update(self):
        first = self.capture()
        self.read_clock = NOW + timedelta(seconds=80)
        self.assertEqual(self.local().load_current(*KEY).queue, self.context.queue)
        renew = self.observe(
            version=1, sha=first["shadow_event_sha256"],
            as_of=NOW + timedelta(seconds=85),
        )
        self.read_clock = NOW + timedelta(seconds=91)
        self.assertEqual(self.local().load_current(*KEY).queue, self.context.queue)
        self.assertEqual(renew["status"], "SHADOW_BLOCKED")

    def test_stale_expected_observation_blocks_without_quarantine(self):
        first = self.capture()
        with self.assertRaises(ShadowQueueBlocked):
            self.observe(version=1, sha=ZERO)
        self.assertEqual(self.shadow.inspect(key=KEY)["status"], "SHADOW_BLOCKED")
        self.assertEqual(self.count("sns_media_shadow_queue_events"), 1)

    def test_event_immutability_and_head_tamper_detection(self):
        self.capture()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE sns_media_shadow_queue_events SET action='DRIFT'",
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM sns_media_shadow_queue_events")
        self.db.execute(
            "UPDATE sns_media_shadow_queue_heads SET snapshot_json=? WHERE queue_id=?",
            ('{"queue":{}}', KEY[2]),
        )
        with self.assertRaises(ShadowQueueBlocked):
            self.shadow.inspect(key=KEY)

    def test_fault_injection_rolls_back_head_event(self):
        self.db.execute(
            """CREATE TRIGGER reject_shadow_event BEFORE INSERT
               ON sns_media_shadow_queue_events
               BEGIN SELECT RAISE(ABORT,'fault'); END""",
        )
        with self.assertRaises(ShadowQueueBlocked):
            self.capture()
        self.assertEqual(self.count("sns_media_shadow_queue_heads"), 0)
        self.assertFalse(self.db.in_transaction)

    def test_second_connection_cannot_import_same_queue_twice(self):
        self.capture()
        other = sqlite3.connect(self.path, isolation_level=None, timeout=2)
        other.execute("PRAGMA foreign_keys=ON")
        try:
            authority = MediaShadowQueueAuthority(other)
            source = CanonicalProtectedReviewReader(
                source=fixtures.Snapshots(self.context),
                vault=ProtectedEvidenceVault(other),
            )
            with self.assertRaises(ShadowQueueBlocked):
                authority.capture(
                    key=KEY, operation_id="shadow_other_connection_20261012_01",
                    expected_version=0, expected_head_sha256=ZERO,
                    verifier=self.make_verifier(other),
                    bearer=self.bearer, trusted_issuer=ISSUER,
                    source=source, as_of=NOW,
                )
            self.assertEqual(self.count("sns_media_shadow_queue_events"), 1)
        finally:
            other.close()

    def test_recursive_capture_of_own_shadow_is_refused(self):
        self.capture()
        self.external = self.local()
        with self.assertRaises(ShadowQueueBlocked):
            self.capture(
                operation="shadow_self_refresh_20261012_000001",
                expected_version=1,
                expected_head_sha256=self.shadow.inspect(key=KEY)["shadow_event_sha256"],
            )

    def test_no_network_sheet_writer_or_authorized_states_in_module(self):
        code = (
            ROOT / "scripts" / "media_shadow_queue_authority.py"
        ).read_text(encoding="utf-8")
        for forbidden in (
            "requests.post(", "SheetsClient(", "gspread",
            "update_queue_item(", "ALLOW_REAL_THREADS_POST",
            "_publish_container(", "publish_authorized=True",
        ):
            self.assertNotIn(forbidden, code)
        self.assertFalse(self.shadow.inspect(key=KEY)["publish_authorized"])


if __name__ == "__main__":
    unittest.main()
