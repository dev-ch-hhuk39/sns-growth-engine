#!/usr/bin/env python3
"""Offline 5B-6B with real RS256 review auth, protected proofs, SQLite CAS.

All examples use ephemeral keys, private temp databases and fake server-owned
readers; no real network, Google Sheets, Threads/X API or runtime permission.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_publish_intent_authority import (  # noqa: E402
    MediaPublishIntents, PublishIntentBlocked, initialize_intent_schema,
)
from media_review_canonical_adapter import CanonicalProtectedReviewReader  # noqa: E402
from media_review_protected_evidence import (  # noqa: E402
    ProtectedEvidenceVault, initialize_trust_schema,
)
from media_review_queue_reconciliation import (  # noqa: E402
    ReviewQueueReconciliation, initialize_reconciliation_schema,
    queue_fingerprint,
)
from media_review_transactional_ledger import (  # noqa: E402
    initialize_review_schema, record_review, revoke_review,
)
from media_review_verified_identity import (  # noqa: E402
    PinnedRS256SessionVerifier, SQLiteSessionAuthority,
)
from test_media_review_trusted_precommit import (  # noqa: E402
    NOW, ISSUER, good_context, good_request,
)

KEY = ("liver_manager", "lm_1800_clip_media", "clip_001")
SUBJECT = "reviewer_0001"
SID = "session_publish_intent_001"
JTI = "jwt_publish_intent_00001"
KID = "key_publish_intent_20261012"
T = int(NOW.timestamp())
OP = "intent_hold_20261012_000001"
NO_RAW = ("never-store-token", "PRIVATE_POST_BODY", "raw_evidence_text",
          "SENSITIVE_EVIDENCE", "https://secret.example")


def b64(value):
    return base64.urlsafe_b64encode(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
    ).decode().rstrip("=")


class Snapshots:
    def __init__(self, context):
        self.context = context
        self.offline = False

    def load(self, account_id, slot_id, queue_id):
        if self.offline:
            raise RuntimeError("provider secret never-store-token")
        if (account_id, slot_id, queue_id) != KEY:
            raise RuntimeError("unauthorized_private_source")
        return (
            copy.deepcopy(self.context.plan),
            copy.deepcopy(self.context.receipts),
            copy.deepcopy(self.context.queue),
        )


class PublishIntentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public = cls.private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    @classmethod
    def token(cls, overrides=None, header=None):
        claims = {
            "iss": ISSUER, "aud": "sns-growth-media-review",
            "sub": SUBJECT, "sid": SID, "jti": JTI, "amr": ["pwd", "mfa"],
            "iat": T - 160, "nbf": T - 161, "exp": T + 3600,
            "auth_time": T - 200, "mfa_at": T - 120,
        }
        claims.update(overrides or {})
        head = {"alg": "RS256", "typ": "JWT", "kid": KID}
        head.update(header or {})
        signed = b64(head) + "." + b64(claims)
        signature = cls.private.sign(
            signed.encode("ascii"), padding.PKCS1v15(), hashes.SHA256(),
        )
        return signed + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "review.db")
        self.db = sqlite3.connect(self.path, isolation_level=None, timeout=2)
        for migration in (
            initialize_review_schema, initialize_trust_schema,
            initialize_reconciliation_schema, initialize_intent_schema,
        ):
            migration(self.db)
        self.jwt = self.token()
        self.bearer = "Bearer " + self.jwt
        self.db.execute(
            """INSERT INTO sns_review_sessions
               (session_id,subject,issuer,token_sha256,token_jti,
                authenticated_at,mfa_at,expires_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (SID, SUBJECT, ISSUER, hashlib.sha256(self.jwt.encode()).hexdigest(),
             JTI, T - 200, T - 120, T + 3600),
        )
        self.db.execute(
            """INSERT INTO sns_review_account_grants
               (subject,account_id,role,enabled) VALUES (?,?,?,1)""",
            (SUBJECT, KEY[0], "MEDIA_REVIEWER"),
        )
        self.verifier = self.make_verifier(self.db)
        self.vault = ProtectedEvidenceVault(self.db)
        self.context = good_context()
        self.source_fixture = Snapshots(self.context)
        for i, proof in enumerate(self.context.evidence_by_id.values()):
            fields = (
                "evidence_id", "kind", "account_id", "slot_id", "queue_id",
                "media_asset_id", "source_id", "usage_scope",
                "allowed_platforms", "allowed_territories",
                "rights_valid_from", "rights_expires_at",
            )
            self.vault.attest(
                metadata={k: copy.deepcopy(proof[k]) for k in fields},
                original_bytes=(f"private_original_evidence_{i}").encode(),
                human_verified_original=True, bearer_token=self.bearer,
                verifier=self.verifier, trusted_issuer=ISSUER,
                operation_id=f"evop_publish_intent_20261012_{i:03d}", as_of=NOW,
            )
        self.canonical = CanonicalProtectedReviewReader(
            source=self.source_fixture, vault=self.vault,
        )
        self.review = replace(
            good_request(self.context),
            expected_queue_sha256=queue_fingerprint(self.context.queue),
        )
        self.guard = ReviewQueueReconciliation(self.db)
        self.intents = MediaPublishIntents(self.db)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    @classmethod
    def make_verifier(cls, db):
        return PinnedRS256SessionVerifier(
            issuer=ISSUER, public_keys_by_kid={KID: cls.public},
            sessions=SQLiteSessionAuthority(db),
        )

    def count(self, table):
        return self.db.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]

    def review_and_match(self):
        record_review(
            self.db, self.review, self.bearer,
            verifier=self.verifier, canonical=self.canonical,
            trusted_issuer=ISSUER, operation_id="op_intent_review_20261012_01",
            expected_ledger_version=0, queue_authority=self.guard, as_of=NOW,
        )
        return self.guard.reconcile_once(
            key=KEY, source=self.canonical,
            operation_id="sync_intent_match_20261012_01",
            expected_binding_version=1, as_of=NOW,
        )

    def reserve(self, operation=OP, as_of=NOW, **override):
        params = {
            "key": KEY, "operation_id": operation, "expected_binding_version": 2,
            "expected_review_version": 1, "verifier": self.verifier,
            "bearer": self.bearer, "trusted_issuer": ISSUER,
            "source": self.canonical, "as_of": as_of,
        }
        params.update(override)
        return self.intents.reserve(**params)

    def recheck(self, *, operation="intent_recheck_20261012_00001", **override):
        params = {
            "key": KEY, "operation_id": operation, "expected_intent_version": 1,
            "verifier": self.verifier, "bearer": self.bearer,
            "trusted_issuer": ISSUER, "source": self.canonical, "as_of": NOW,
        }
        params.update(override)
        return self.intents.recheck(**params)

    def cancel(self, *, operation="intent_cancel_20261012_000001", **override):
        params = {
            "key": KEY, "operation_id": operation, "expected_intent_version": 1,
            "verifier": self.verifier, "bearer": self.bearer,
            "trusted_issuer": ISSUER, "as_of": NOW,
        }
        params.update(override)
        return self.intents.cancel(**params)

    def test_migration_requires_existing_trusted_sources(self):
        empty = sqlite3.connect(":memory:", isolation_level=None)
        try:
            with self.assertRaisesRegex(
                PublishIntentBlocked, "intent_prerequisite_migration_missing",
            ):
                initialize_intent_schema(empty)
        finally:
            empty.close()

    def test_no_review_or_unmatched_reconciliation_never_records_intent(self):
        with self.assertRaises(PublishIntentBlocked):
            self.reserve()
        self.assertEqual(self.count("sns_media_publish_intent_heads"), 0)
        record_review(
            self.db, self.review, self.bearer,
            verifier=self.verifier, canonical=self.canonical,
            trusted_issuer=ISSUER, operation_id="op_intent_review_20261012_01",
            expected_ledger_version=0, queue_authority=self.guard, as_of=NOW,
        )
        with self.assertRaisesRegex(PublishIntentBlocked, "intent_review_or_binding_not_current"):
            self.reserve(expected_binding_version=1)
        self.assertEqual(self.count("sns_media_publish_intent_events"), 0)

    def test_signed_review_verified_proof_and_reconciled_intent_still_blocked(self):
        self.review_and_match()
        old = copy.deepcopy(self.context)
        result = self.reserve()
        self.assertEqual(result["status"], "HELD_BLOCKED")
        self.assertEqual(result["intent_version"], 1)
        self.assertIs(result["publish_authorized"], False)
        self.assertIs(result["effective_approval"], False)
        self.assertIs(result["publish_attempted"], False)
        self.assertFalse(result["external_queue_atomicity_guaranteed"])
        self.assertEqual(self.count("sns_media_publish_intent_heads"), 1)
        self.assertEqual(self.count("sns_media_publish_intent_events"), 1)
        self.assertEqual(self.intents.inspect(key=KEY)["status"], "HELD_BLOCKED")
        payload = self.db.execute(
            "SELECT payload_json FROM sns_media_publish_intent_events",
        ).fetchone()[0]
        for term in (*NO_RAW, self.jwt, "private_original_evidence"):
            self.assertNotIn(term, payload)
        self.assertEqual(self.context, old)

    def test_claim_replay_or_changed_expected_version_is_denied(self):
        self.review_and_match()
        self.reserve()
        for operation, version in (
            (OP, 2), ("intent_other_hold_20261012_02", 2),
            ("intent_other_hold_20261012_03", 1),
        ):
            with self.subTest(op=operation), self.assertRaises(PublishIntentBlocked):
                self.reserve(operation=operation, expected_binding_version=version)
        self.assertEqual(self.count("sns_media_publish_intent_events"), 1)

    def test_missing_token_wrong_session_or_disabled_grant_fail_closed(self):
        self.review_and_match()
        with self.assertRaises(PublishIntentBlocked):
            self.reserve(bearer="Bearer invalid-token")
        with self.assertRaises(PublishIntentBlocked):
            self.reserve(bearer="Bearer " + self.token({"aud": "other"}))
        self.db.execute(
            "UPDATE sns_review_account_grants SET enabled=0 WHERE subject=?",
            (SUBJECT,),
        )
        with self.assertRaises(PublishIntentBlocked):
            self.reserve()
        self.assertEqual(self.count("sns_media_publish_intent_events"), 0)

    def test_revoked_auth_session_or_review_grant_blocks_preflight(self):
        self.review_and_match()
        # A user may have passed review, but explicit user/session revocation
        # invalidates future intent checking.
        self.db.execute(
            "UPDATE sns_review_sessions SET revoked_at=? WHERE session_id=?",
            (T, SID),
        )
        with self.assertRaises(PublishIntentBlocked):
            self.reserve()
        self.assertEqual(self.count("sns_media_publish_intent_heads"), 0)

    def test_tampered_caption_same_revision_not_reservable(self):
        self.review_and_match()
        self.context.queue["public_post_text"] = "PRIVATE_POST_BODY_CHANGED"
        with self.assertRaises(PublishIntentBlocked):
            self.reserve()
        self.assertEqual(self.count("sns_media_publish_intent_heads"), 0)

    def test_proof_revocation_or_quality_loss_before_reserve_blocks(self):
        self.review_and_match()
        proof = next(iter(self.context.evidence_by_id))
        self.vault.revoke(
            evidence_id=proof, bearer_token=self.bearer,
            verifier=self.verifier, trusted_issuer=ISSUER,
            operation_id="evop_intent_revoke_20261012_01",
            expected_revision=1, as_of=NOW,
        )
        with self.assertRaises(PublishIntentBlocked):
            self.reserve()
        self.assertEqual(self.count("sns_media_publish_intent_events"), 0)

    def test_rights_age_or_expiry_fail_closed(self):
        self.review_and_match()
        with self.assertRaises(PublishIntentBlocked):
            self.reserve(as_of=NOW + timedelta(hours=26))
        self.assertEqual(self.count("sns_media_publish_intent_heads"), 0)

    def test_cancel_is_atomic_even_if_source_goes_offline(self):
        self.review_and_match()
        self.reserve()
        self.source_fixture.offline = True
        result = self.cancel()
        self.assertEqual(result["status"], "CANCELLED_BLOCKED")
        self.assertFalse(result["publish_authorized"])
        self.assertEqual(self.count("sns_media_publish_intent_events"), 2)
        with self.assertRaises(PublishIntentBlocked):
            self.reserve(operation="intent_post_cancel_hold_20261012_01")
        with self.assertRaises(PublishIntentBlocked):
            self.cancel(operation="intent_cancel_twice_20261012_02",
                        expected_intent_version=2)

    def test_recheck_unchanged_stays_held_without_new_event(self):
        self.review_and_match()
        self.reserve()
        result = self.recheck()
        self.assertEqual(result["status"], "HELD_BLOCKED")
        self.assertTrue(result["source_rechecked"])
        self.assertFalse(result["publish_authorized"])
        self.assertEqual(self.count("sns_media_publish_intent_events"), 1)

    def test_recheck_rights_withdrawal_quarantines_permanently(self):
        self.review_and_match()
        self.reserve()
        proof = next(iter(self.context.evidence_by_id))
        self.vault.revoke(
            evidence_id=proof, bearer_token=self.bearer,
            verifier=self.verifier, trusted_issuer=ISSUER,
            operation_id="evop_intent_revoke_20261012_02",
            expected_revision=1, as_of=NOW,
        )
        result = self.recheck()
        self.assertEqual(result["status"], "QUARANTINED_BLOCKED")
        self.assertFalse(result["publish_authorized"])
        with self.assertRaises(PublishIntentBlocked):
            self.recheck(operation="intent_again_recheck_20261012_02",
                         expected_intent_version=2)

    def test_recheck_unavailable_source_quarantines_and_redacts(self):
        self.review_and_match()
        self.reserve()
        self.source_fixture.offline = True
        result = self.recheck()
        self.assertEqual(result["status"], "QUARANTINED_BLOCKED")
        payload = self.db.execute(
            "SELECT payload_json FROM sns_media_publish_intent_events ORDER BY version DESC LIMIT 1",
        ).fetchone()[0]
        self.assertIn("source_unavailable", payload)
        self.assertNotIn("never-store-token", payload)

    def test_recheck_expiry_quarantines_not_releases(self):
        self.review_and_match()
        self.reserve()
        result = self.recheck(as_of=NOW + timedelta(minutes=6))
        self.assertEqual(result["status"], "QUARANTINED_BLOCKED")
        self.assertFalse(result["publish_authorized"])

    def test_recheck_queue_content_drift_quarantines(self):
        self.review_and_match()
        self.reserve()
        self.context.queue["public_post_text"] += " version2"
        result = self.recheck()
        self.assertEqual(result["status"], "QUARANTINED_BLOCKED")
        self.assertEqual(self.intents.inspect(key=KEY)["status"], "QUARANTINED_BLOCKED")

    def test_recheck_review_revocation_cannot_reenable(self):
        self.review_and_match()
        self.reserve()
        revoke_review(
            self.db, self.review, self.bearer,
            verifier=self.verifier, trusted_issuer=ISSUER,
            operation_id="op_intent_review_revoke_00001",
            expected_ledger_version=1, reason_code="consent_withdrawn",
            queue_authority=self.guard, as_of=NOW,
        )
        self.assertEqual(self.recheck()["status"], "QUARANTINED_BLOCKED")

    def test_recheck_wrong_expected_version_and_duplicate_operation(self):
        self.review_and_match()
        self.reserve()
        self.assertRaises(
            PublishIntentBlocked, self.recheck, expected_intent_version=2,
        )
        self.cancel()
        with self.assertRaises(PublishIntentBlocked):
            self.cancel(operation="intent_cancel_again_20261012_01",
                        expected_intent_version=2)
        self.assertEqual(self.count("sns_media_publish_intent_events"), 2)

    def test_sqlite_precommit_failure_rolls_back_entire_reservation(self):
        self.review_and_match()
        self.db.execute(
            """CREATE TRIGGER reject_intent_event BEFORE INSERT
               ON sns_media_publish_intent_events
               BEGIN SELECT RAISE(ABORT, 'fault_injection'); END""",
        )
        with self.assertRaises(PublishIntentBlocked):
            self.reserve()
        self.assertEqual(self.count("sns_media_publish_intent_heads"), 0)
        self.assertFalse(self.db.in_transaction)

    def test_events_immutable_and_head_tampering_detected(self):
        self.review_and_match()
        self.reserve()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE sns_media_publish_intent_events SET action='CANCEL'",
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("DELETE FROM sns_media_publish_intent_events")
        self.db.execute(
            "UPDATE sns_media_publish_intent_heads SET queue_sha256=? WHERE queue_id=?",
            ("f" * 64, KEY[2]),
        )
        with self.assertRaisesRegex(PublishIntentBlocked, "intent_head_tampered"):
            self.intents.inspect(key=KEY)

    def test_different_connection_cannot_claim_same_review(self):
        self.review_and_match()
        self.reserve()
        other = sqlite3.connect(self.path, isolation_level=None, timeout=2)
        other.execute("PRAGMA foreign_keys=ON")
        try:
            authority = MediaPublishIntents(other)
            canonical = CanonicalProtectedReviewReader(
                source=Snapshots(self.context), vault=ProtectedEvidenceVault(other),
            )
            with self.assertRaises(PublishIntentBlocked):
                authority.reserve(
                    key=KEY, operation_id="intent_dual_20261012_00001",
                    expected_binding_version=2, expected_review_version=1,
                    verifier=self.make_verifier(other), bearer=self.bearer,
                    trusted_issuer=ISSUER, source=canonical, as_of=NOW,
                )
            self.assertEqual(self.count("sns_media_publish_intent_events"), 1)
        finally:
            other.close()

    def test_unique_asset_and_content_identity_are_conservative(self):
        self.review_and_match()
        self.reserve()
        # SQL uniqueness holds across distinct queue IDs even if code is
        # accidentally modified; cannot insert cloned content/asset silently.
        self.db.execute(
            """INSERT INTO sns_media_review_heads
               (account_id,slot_id,queue_id) VALUES (?,?,?)""",
            (KEY[0], KEY[1], "clip_002"),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                """INSERT INTO sns_media_publish_intent_heads
                   (account_id,slot_id,queue_id,version,state,queue_sha256,
                    context_sha256,content_sha256,media_asset_id,source_id,
                    review_version,review_event_sha256,binding_version,
                    binding_event_sha256,held_until,last_event_sha256,updated_at)
                   SELECT account_id,slot_id,'clip_002',version,state,queue_sha256,
                    context_sha256,content_sha256,media_asset_id,source_id,
                    review_version,review_event_sha256,binding_version,
                    binding_event_sha256,held_until,last_event_sha256,updated_at
                   FROM sns_media_publish_intent_heads WHERE queue_id=?""", (KEY[2],),
            )
        self.assertEqual(self.count("sns_media_publish_intent_heads"), 1)

    def test_no_publish_api_or_ready_writes_in_service(self):
        text = (ROOT / "scripts" / "media_publish_intent_authority.py").read_text()
        for unsafe in (
            "requests.post(", "gspread", "update_queue_item(", "publish(",
            "threads_publish", "PUBLISH_ENABLED", "ALLOW_MEDIA_POSTS",
        ):
            self.assertNotIn(unsafe, text)
        self.assertFalse(self.intents.inspect(key=KEY)["publish_authorized"])


if __name__ == "__main__":
    unittest.main()
