#!/usr/bin/env python3
"""6N independent signed two-operator, single-operation reporting canary gate.

This file NEVER issues operator credentials or signs approval JWTs.
An authorized operations/IdP process outside this repository must issue
two independently signed and deliberately scoped JWTs. An approving
human's identity is pinned per operator signing key by trusted server
configuration; neither the Sheets service JWT nor the reviewer JWT is
accepted as an operator approval.

SQLite replay rows are inserted in exactly the SAME local transaction as
the protected reporting delivery PREPARE. This does not make Google Sheets
writes atomic with SQLite, nor grant SNS publishing authority.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from media_mirror_operator_grants import (
    OperatorGrantBlocked, require_current_operator_grant,
)
from media_mirror_operator_idp import (
    OperatorIdentityBlocked, PinnedOperatorIdpSessionVerifier,
)
from media_review_trusted_precommit import _utc
from media_review_verified_identity import SAFE_NAME, _epoch, _json_object, _unbase

MIGRATION = (
    Path(__file__).resolve().parents[1] / "db" / "migrations"
    / "0011_sns_reporting_canary_two_operator_signoff.sql"
)
AUDIENCE = "sns-growth-reporting-canary-operator-approval"
TOKEN_USE = "single_reporting_canary_approval"
SCOPE = "mirror:reporting:canary:approve"
SHA = re.compile(r"[0-9a-f]{64}\Z")
OPERATION = re.compile(r"delivery_[A-Za-z0-9_.:-]{12,100}\Z")


class CanaryApprovalBlocked(ValueError):
    """Sanitized error; never contains JWT contents, signatures or secrets."""


@dataclass(frozen=True)
class _OperatorProof:
    subject: str
    kid: str
    jti: str
    token_sha256: str


def initialize_canary_approval_schema(db: sqlite3.Connection) -> None:
    """Explicit local migration only; no production schema changes."""
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise CanaryApprovalBlocked("canary_migration_requires_autocommit")
    try:
        for table in (
            "sns_mirror_delivery_heads",
            "sns_mirror_delivery_destinations",
            "sns_media_mirror_outbox_heads",
        ):
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone() is None:
                raise CanaryApprovalBlocked("canary_migration_prerequisite_missing")
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
        db.execute("PRAGMA foreign_keys=ON")
    except (sqlite3.Error, OSError):
        raise CanaryApprovalBlocked("canary_migration_failed") from None


class PinnedTwoOperatorCanaryVerifier:
    """Verifies 2 different pinned humans and records consumed JWT JTIs.

    Config: {kid: (pinned_operator_subject, public_RSA_PEM)}. These human
    operator keys must be managed independently of the reporting writer,
    reviewer JWT signing and repository runtime. The config must not
    originate in user input or any Google Sheets cell.
    """

    def __init__(
        self, *, db: sqlite3.Connection, issuer: str,
        operators_by_kid: Mapping[str, tuple[str, bytes]],
        identity_verifier: PinnedOperatorIdpSessionVerifier | None = None,
    ) -> None:
        if (not isinstance(db, sqlite3.Connection)
                or not isinstance(issuer, str)
                or not issuer.startswith("https://")
                or not operators_by_kid
                or len(operators_by_kid) < 2):
            raise CanaryApprovalBlocked("canary_operator_configuration_invalid")
        pairs: dict[str, tuple[str, rsa.RSAPublicKey]] = {}
        try:
            for kid, configuration in operators_by_kid.items():
                if (not isinstance(kid, str)
                        or SAFE_NAME.fullmatch(kid) is None
                        or not isinstance(configuration, tuple)
                        or len(configuration) != 2):
                    raise CanaryApprovalBlocked("canary_operator_key_untrusted")
                subject, pem = configuration
                if not isinstance(subject, str) or SAFE_NAME.fullmatch(subject) is None:
                    raise CanaryApprovalBlocked("canary_operator_subject_untrusted")
                key = serialization.load_pem_public_key(pem)
                if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
                    raise CanaryApprovalBlocked("canary_operator_key_untrusted")
                pairs[kid] = (subject, key)
        except (TypeError, ValueError):
            raise CanaryApprovalBlocked("canary_operator_key_untrusted") from None
        if len(set(p[0] for p in pairs.values())) < 2:
            raise CanaryApprovalBlocked("canary_two_distinct_operators_required")
        fingerprints = {
            hashlib.sha256(
                key.public_bytes(
                    serialization.Encoding.DER,
                    serialization.PublicFormat.SubjectPublicKeyInfo,
                )
            ).hexdigest()
            for _subject, key in pairs.values()
        }
        if len(fingerprints) != len(pairs):
            raise CanaryApprovalBlocked("canary_operator_key_material_reused")
        if identity_verifier is not None and (
                type(identity_verifier) is not PinnedOperatorIdpSessionVerifier
                or identity_verifier.db is not db):
            raise CanaryApprovalBlocked("canary_idp_binding_invalid")
        self.db, self.issuer, self.operators = db, issuer, pairs
        self.identity_verifier = identity_verifier

    def _verify_one(
        self, *, token: str, event_sha256: str, operation_id: str,
        destination_id: str, account_id: str, slot_id: str, queue_id: str,
        row_number: int, projection_sha256: str, service_subject: str,
        now: datetime, approval_slot: int, identity_token: str,
    ) -> _OperatorProof:
        if not isinstance(token, str) or not 16 <= len(token) <= 4096:
            raise CanaryApprovalBlocked("canary_operator_jwt_invalid")
        parts = token.split(".")
        if len(parts) != 3:
            raise CanaryApprovalBlocked("canary_operator_jwt_invalid")
        a, b, c = parts
        try:
            header = _json_object(_unbase(a))
            claims = _json_object(_unbase(b))
            signature = _unbase(c)
        except Exception:
            raise CanaryApprovalBlocked("canary_operator_jwt_invalid") from None
        kid = header.get("kid")
        if (header.get("alg") != "RS256" or header.get("typ") != "JWT"
                or not isinstance(kid, str) or kid not in self.operators):
            raise CanaryApprovalBlocked("canary_operator_signature_invalid")
        pinned_subject, key = self.operators[kid]
        try:
            key.verify(
                signature, (a + "." + b).encode("ascii"),
                padding.PKCS1v15(), hashes.SHA256(),
            )
        except (InvalidSignature, ValueError):
            raise CanaryApprovalBlocked("canary_operator_signature_invalid") from None
        if (claims.get("iss") != self.issuer
                or claims.get("aud") != AUDIENCE
                or claims.get("token_use") != TOKEN_USE
                or claims.get("scope") != SCOPE
                or claims.get("sub") != pinned_subject
                or claims.get("sub") == service_subject):
            raise CanaryApprovalBlocked("canary_operator_claims_invalid")
        jti = claims.get("jti")
        if not isinstance(jti, str) or SAFE_NAME.fullmatch(jti) is None:
            raise CanaryApprovalBlocked("canary_operator_jti_invalid")
        expected = {
            "event_sha256": event_sha256,
            "operation_id": operation_id,
            "destination_id": destination_id,
            "account_id": account_id,
            "slot_id": slot_id,
            "queue_id": queue_id,
            "row_number": row_number,
            "projection_sha256": projection_sha256,
            "approval_slot": approval_slot,
        }
        if any(
            type(claims.get(k)) is not type(v) or claims.get(k) != v
            for k, v in expected.items()
        ):
            raise CanaryApprovalBlocked("canary_operator_target_mismatch")
        try:
            issued, not_before, expiry = (
                _epoch(claims, "iat"), _epoch(claims, "nbf"),
                _epoch(claims, "exp"),
            )
        except Exception:
            raise CanaryApprovalBlocked("canary_operator_time_invalid") from None
        now_seconds = now.timestamp()
        if (issued > now_seconds + 30
                or not_before > now_seconds + 30
                or expiry <= now_seconds
                or expiry <= issued or expiry - issued > 300
                or issued < now_seconds - 300):
            raise CanaryApprovalBlocked("canary_operator_time_invalid")
        grant_generation = claims.get("grant_generation")
        try:
            require_current_operator_grant(
                self.db, kid=kid, subject=pinned_subject,
                account_id=account_id, destination_id=destination_id,
                approval_slot=approval_slot,
                grant_generation=grant_generation,
                issued_at=issued, expires_at=expiry,
                now_seconds=int(now_seconds),
            )
        except OperatorGrantBlocked:
            raise CanaryApprovalBlocked("canary_operator_grant_denied") from None
        if self.identity_verifier is None:
            raise CanaryApprovalBlocked("canary_idp_identity_required")
        idp_session_id = claims.get("idp_session_id")
        idp_assertion_sha256 = claims.get("idp_assertion_sha256")
        try:
            self.identity_verifier.verify_active(
                token=identity_token, subject=pinned_subject,
                expected_session_id=idp_session_id,
                expected_sha256=idp_assertion_sha256, now=now,
            )
        except OperatorIdentityBlocked:
            raise CanaryApprovalBlocked("canary_idp_identity_denied") from None
        return _OperatorProof(
            subject=pinned_subject, kid=kid, jti=jti,
            token_sha256=hashlib.sha256(token.encode("ascii")).hexdigest(),
        )

    def require_current_consumed(
        self, *, tokens: tuple[str, str], event_sha256: str,
        operation_id: str, destination_id: str,
        account_id: str, slot_id: str, queue_id: str,
        row_number: int, projection_sha256: str,
        service_subject: str, as_of: datetime,
        identity_tokens: tuple[str,str],
    ) -> None:
        """JIT verification before PUT; never consumes or signs a new token.

        The caller holds a SQLite read transaction. Refuse a revoked,
        disabled or generation-mismatched operator *even after PREPARED*.
        The signoff rows must still match the exact originally consumed
        signatures, event and operation, not merely two new valid JWTs.
        """
        if not self.db.in_transaction:
            raise CanaryApprovalBlocked("canary_atomic_read_required")
        if (not isinstance(tokens, tuple) or len(tokens) != 2
                or any(type(v) is not str for v in tokens)
                or not isinstance(identity_tokens, tuple)
                or len(identity_tokens) != 2
                or any(type(v) is not str for v in identity_tokens)):
            raise CanaryApprovalBlocked("canary_operator_identity_missing")
        now = _utc(as_of, "canary_operator_clock_invalid")
        proofs = [
            self._verify_one(
                token=t, event_sha256=event_sha256,
                operation_id=operation_id,
                destination_id=destination_id,
                account_id=account_id,
                slot_id=slot_id, queue_id=queue_id,
                row_number=row_number,
                projection_sha256=projection_sha256,
                service_subject=service_subject, now=now,
                approval_slot=index,
                identity_token=identity_tokens[index-1],
            )
            for index, t in enumerate(tokens, 1)
        ]
        if proofs[0].kid == proofs[1].kid or proofs[0].subject == proofs[1].subject:
            raise CanaryApprovalBlocked("canary_two_distinct_operators_required")
        try:
            rows = self.db.execute(
                """SELECT operator_slot,signer_kid,signer_subject,signer_jti,
                          signed_token_sha256,account_id,row_number,
                          projection_sha256
                   FROM sns_mirror_canary_signoff_uses
                   WHERE event_sha256=? AND destination_id=?
                     AND operation_id=? ORDER BY operator_slot""",
                (event_sha256,destination_id,operation_id),
            ).fetchall()
        except sqlite3.Error:
            raise CanaryApprovalBlocked("canary_signoff_journal_unavailable") from None
        expected = [
            (index,p.kid,p.subject,p.jti,p.token_sha256,account_id,
             row_number,projection_sha256)
            for index,p in enumerate(proofs,1)
        ]
        if rows != expected:
            raise CanaryApprovalBlocked("canary_signoff_journal_mismatch")

    def verify_and_consume(
        self, *, tokens: tuple[str, str], event_sha256: str,
        operation_id: str, destination_id: str,
        account_id: str, slot_id: str, queue_id: str,
        row_number: int, projection_sha256: str,
        service_subject: str, as_of: datetime,
        identity_tokens: tuple[str,str],
    ) -> None:
        """Called only WITHIN the same BEGIN IMMEDIATE as delivery PREPARE."""
        if not self.db.in_transaction:
            raise CanaryApprovalBlocked("canary_atomic_transaction_required")
        if (not isinstance(tokens, tuple) or len(tokens) != 2
                or type(tokens[0]) is not str or type(tokens[1]) is not str
                or not isinstance(identity_tokens, tuple)
                or len(identity_tokens) != 2
                or any(type(v) is not str for v in identity_tokens)
                or not isinstance(event_sha256, str)
                or SHA.fullmatch(event_sha256) is None
                or not isinstance(projection_sha256, str)
                or SHA.fullmatch(projection_sha256) is None
                or not isinstance(operation_id, str)
                or OPERATION.fullmatch(operation_id) is None
                or type(row_number) is not int
                or not 2 <= row_number <= 10000):
            raise CanaryApprovalBlocked("canary_operator_approval_missing")
        now = _utc(as_of, "canary_operator_clock_invalid")
        proofs = [
            self._verify_one(
                token=token, event_sha256=event_sha256,
                operation_id=operation_id, destination_id=destination_id,
                account_id=account_id, slot_id=slot_id, queue_id=queue_id,
                row_number=row_number, projection_sha256=projection_sha256,
                service_subject=service_subject, now=now,
                approval_slot=index,
                identity_token=identity_tokens[index-1],
            )
            for index, token in enumerate(tokens, 1)
        ]
        if (proofs[0].subject == proofs[1].subject
                or proofs[0].kid == proofs[1].kid
                or proofs[0].jti == proofs[1].jti
                or proofs[0].token_sha256 == proofs[1].token_sha256):
            raise CanaryApprovalBlocked("canary_two_distinct_operators_required")
        try:
            for index, p in enumerate(proofs, 1):
                self.db.execute(
                    """INSERT INTO sns_mirror_canary_signoff_uses(
                       signer_jti,signer_kid,signer_subject,
                       signed_token_sha256,event_sha256,destination_id,
                       account_id,row_number,projection_sha256,operation_id,
                       operator_slot,consumed_at
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        p.jti, p.kid, p.subject, p.token_sha256,
                        event_sha256, destination_id, account_id, row_number,
                        projection_sha256, operation_id, index,
                        int(now.timestamp()),
                    ),
                )
        except sqlite3.Error:
            raise CanaryApprovalBlocked("canary_approval_used_or_store_unavailable") from None
