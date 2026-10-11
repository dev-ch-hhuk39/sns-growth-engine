#!/usr/bin/env python3
"""Phase 5B-5B offline contract/security and ledger integration checks."""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import sqlite3
import sys
import unittest
from datetime import timedelta
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_review_verified_identity import (  # noqa: E402
    PinnedRS256SessionVerifier, SQLiteSessionAuthority, IdentityBlocked,
)
from media_review_protected_evidence import (  # noqa: E402
    initialize_trust_schema, ProtectedEvidenceVault, EvidenceBlocked,
)
from media_review_canonical_adapter import (  # noqa: E402
    CanonicalProtectedReviewReader,
)
from media_review_transactional_ledger import (  # noqa: E402
    initialize_review_schema, record_review,
)
from test_media_review_trusted_precommit import (  # noqa: E402
    NOW, ISSUER, good_context, good_request,
)

KID = "review-key-20261011"
SID = "session_review_001"
JTI = "id_token_20261011"
SUB = "reviewer_0001"
ACCOUNT = "liver_manager"
T = int(NOW.timestamp())


def b64(obj):
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


class Snapshots:
    def __init__(self, context):
        self.context = context

    def load(self, account_id, slot_id, queue_id):
        assert (account_id, slot_id, queue_id) == (
            "liver_manager", "lm_1800_clip_media", "clip_001",
        )
        c = self.context
        return copy.deepcopy(c.plan), copy.deepcopy(c.receipts), copy.deepcopy(c.queue)


class TrustedAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.public = cls.private.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

    def token(self, overrides=None, header=None):
        claims = {
            "iss": ISSUER, "aud": "sns-growth-media-review", "sub": SUB,
            "sid": SID, "jti": JTI, "amr": ["pwd", "mfa"],
            "iat": T - 200, "nbf": T - 201, "exp": T + 3600,
            "auth_time": T - 220, "mfa_at": T - 120,
        }
        claims.update(overrides or {})
        h = {"alg": "RS256", "kid": KID, "typ": "JWT"}
        h.update(header or {})
        data = b64(h) + "." + b64(claims)
        signature = self.private.sign(
            data.encode(), padding.PKCS1v15(), hashes.SHA256(),
        )
        return data + "." + base64.urlsafe_b64encode(signature).decode().rstrip("=")

    def setUp(self):
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        initialize_trust_schema(self.db)
        initialize_review_schema(self.db)
        self.bearer = self.token()
        self.db.execute(
            """INSERT INTO sns_review_sessions
               (session_id,subject,issuer,token_sha256,token_jti,
                authenticated_at,mfa_at,expires_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (SID, SUB, ISSUER, hashlib.sha256(self.bearer.encode()).hexdigest(),
             JTI, T - 220, T - 120, T + 3600),
        )
        self.db.execute(
            """INSERT INTO sns_review_account_grants
               (subject,account_id,role,enabled) VALUES (?,?,?,1)""",
            (SUB, ACCOUNT, "MEDIA_REVIEWER"),
        )
        self.verifier = PinnedRS256SessionVerifier(
            issuer=ISSUER, public_keys_by_kid={KID: self.public},
            sessions=SQLiteSessionAuthority(self.db),
        )
        self.vault = ProtectedEvidenceVault(self.db)
        self.context = good_context()
        self.request = good_request(self.context)

    def tearDown(self):
        self.db.close()

    def record_all(self):
        for i, proof in enumerate(self.context.evidence_by_id.values()):
            keys = (
                "evidence_id", "kind", "account_id", "slot_id", "queue_id",
                "media_asset_id", "source_id", "usage_scope",
                "allowed_platforms", "allowed_territories",
                "rights_valid_from", "rights_expires_at",
            )
            metadata = {k: copy.deepcopy(proof[k]) for k in keys}
            self.vault.attest(
                metadata=metadata, original_bytes=("verified original " + str(i)).encode(),
                human_verified_original=True,
                bearer_token="Bearer " + self.bearer, verifier=self.verifier,
                trusted_issuer=ISSUER,
                operation_id=f"evop_original_20261011_{i:03d}", as_of=NOW,
            )

    def test_real_signature_grant_vault_canonical_and_isolated_ledger(self):
        self.record_all()
        reader = CanonicalProtectedReviewReader(
            source=Snapshots(self.context), vault=self.vault,
        )
        result = record_review(
            self.db, self.request, "Bearer " + self.bearer,
            verifier=self.verifier, canonical=reader, trusted_issuer=ISSUER,
            operation_id="op_verified_review_00000001",
            expected_ledger_version=0, as_of=NOW,
        )
        self.assertEqual(result["ledger_version"], 1)
        self.assertFalse(result["publish_authorized"])
        self.assertFalse(result["effective_approval"])
        self.assertFalse(result["authenticated_approval_integrated"])
        self.assertFalse(result["external_queue_atomicity_guaranteed"])

    def test_wrong_algorithm_issuer_audience_expiry_mfa_signature(self):
        for overrides, header in (
            ({"iss": "https://impostor.example"}, None),
            ({"aud": "other-app"}, None),
            ({"exp": T - 1}, None),
            ({"nbf": T + 400}, None),
            ({"amr": ["pwd"]}, None),
            ({}, {"alg": "none"}),
            ({}, {"kid": "unknown-review-key"}),
        ):
            with self.subTest(overrides=overrides, header=header):
                with self.assertRaises(IdentityBlocked):
                    self.verifier.verify(self.token(overrides, header), now=NOW)
        bad = self.bearer[:-8] + "AAAAAAAA"
        with self.assertRaises(IdentityBlocked):
            self.verifier.verify(bad, now=NOW)

    def test_revoked_disabled_scope_and_replay_are_blocked(self):
        self.assertEqual(
            self.verifier.verify(self.bearer, now=NOW).subject, SUB,
        )
        self.db.execute(
            "UPDATE sns_review_account_grants SET enabled=0 WHERE subject=?", (SUB,),
        )
        with self.assertRaisesRegex(IdentityBlocked, "reviewer_not_authorized"):
            self.verifier.verify(self.bearer, now=NOW)
        self.db.execute(
            "UPDATE sns_review_account_grants SET enabled=1 WHERE subject=?", (SUB,),
        )
        self.db.execute(
            "UPDATE sns_review_sessions SET revoked_at=? WHERE session_id=?",
            (T, SID),
        )
        with self.assertRaisesRegex(IdentityBlocked, "session_not_active"):
            self.verifier.verify(self.bearer, now=NOW)

    def test_evidence_mutation_replay_and_revocation(self):
        self.record_all()
        proof_id = next(iter(self.context.evidence_by_id))
        first = self.vault.get_current(proof_id)
        self.assertFalse(first["revoked"])
        with self.assertRaises(EvidenceBlocked):
            self.vault.revoke(
                evidence_id=proof_id, bearer_token="Bearer " + self.bearer,
                verifier=self.verifier, trusted_issuer=ISSUER,
                operation_id="evop_revoke_00000000001", expected_revision=0,
                as_of=NOW,
            )
        self.assertEqual(self.vault.revoke(
            evidence_id=proof_id, bearer_token="Bearer " + self.bearer,
            verifier=self.verifier, trusted_issuer=ISSUER,
            operation_id="evop_revoke_00000000001", expected_revision=1,
            as_of=NOW,
        ), 2)
        self.assertTrue(self.vault.get_current(proof_id)["revoked"])
        with self.assertRaises(EvidenceBlocked):
            self.vault.revoke(
                evidence_id=proof_id, bearer_token="Bearer " + self.bearer,
                verifier=self.verifier, trusted_issuer=ISSUER,
                operation_id="evop_revoke_00000000001", expected_revision=2,
                as_of=NOW,
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute(
                "UPDATE sns_review_evidence_events SET original_bytes=? WHERE evidence_id=?",
                (b"changed", proof_id),
            )
        reader = CanonicalProtectedReviewReader(
            source=Snapshots(self.context), vault=self.vault,
        )
        with self.assertRaises(Exception):
            record_review(
                self.db, self.request, "Bearer " + self.bearer,
                verifier=self.verifier, canonical=reader, trusted_issuer=ISSUER,
                operation_id="op_verified_review_00000002",
                expected_ledger_version=0, as_of=NOW,
            )
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM sns_media_review_events").fetchone()[0],
            0,
        )


if __name__ == "__main__":
    unittest.main()
