#!/usr/bin/env python3
"""6P protected, independent IdP proof for a human reporting-canary approver.

The IdP JWT and active session row MUST originate from an independently
authenticated, trusted identity provider process. This module only verifies
provider-signed assertions against server-pinned keys and a protected SQLite
session, with phishing-resistant MFA freshness. It cannot log a user in,
issue a token, bootstrap session rows, or authorize a Sheets write.
"""
from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from media_review_trusted_precommit import _utc
from media_review_verified_identity import (
    SAFE_NAME, _epoch, _json_object, _unbase,
)

MIGRATION = (
    Path(__file__).resolve().parents[1] / "db" / "migrations"
    / "0013_sns_canary_idp_sessions.sql"
)
AUDIENCE = "sns-growth-canary-human-identity"
TOKEN_USE = "canary_operator_identity"
SCOPE = "canary:human:identify"
ACR = "urn:chadult:acr:phishing-resistant"
PROFILE = "PHISHING_RESISTANT_MFA"


class OperatorIdentityBlocked(ValueError):
    """Stable sanitized code; never exposes IdP proofs or identity content."""


def initialize_operator_idp_schema(db: sqlite3.Connection) -> None:
    """Explicit offline migration; production migrations require ops approval."""
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise OperatorIdentityBlocked("canary_idp_migration_requires_autocommit")
    try:
        for name in (
            "sns_mirror_canary_operator_grants",
            "sns_mirror_canary_signoff_uses",
        ):
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (name,),
            ).fetchone() is None:
                raise OperatorIdentityBlocked("canary_idp_prerequisite_missing")
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
        db.execute("PRAGMA foreign_keys=ON")
    except (sqlite3.Error, OSError):
        raise OperatorIdentityBlocked("canary_idp_migration_failed") from None


class PinnedOperatorIdpSessionVerifier:
    """RS256 IdP validation, separate issuer and signing keys from approvers.

    A trusted provider callback must externally provision token digest,
    subject, active session, authentication/MFA timestamps and revocation.
    The verifier never creates session grants or trusts client JWKs.
    """

    def __init__(
        self, *, db: sqlite3.Connection, issuer: str,
        public_keys_by_kid: Mapping[str, bytes],
    ) -> None:
        if (not isinstance(db, sqlite3.Connection)
                or not isinstance(issuer, str) or not issuer.startswith("https://")
                or not public_keys_by_kid):
            raise OperatorIdentityBlocked("canary_idp_config_invalid")
        keys: dict[str, rsa.RSAPublicKey] = {}
        try:
            for kid, pem in public_keys_by_kid.items():
                if not isinstance(kid, str) or SAFE_NAME.fullmatch(kid) is None:
                    raise OperatorIdentityBlocked("canary_idp_key_invalid")
                key = serialization.load_pem_public_key(pem)
                if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
                    raise OperatorIdentityBlocked("canary_idp_key_invalid")
                keys[kid] = key
        except (TypeError, ValueError):
            raise OperatorIdentityBlocked("canary_idp_key_invalid") from None
        self.db, self.issuer, self.keys = db, issuer, keys

    def verify_active(
        self, *, token: str, subject: str, expected_session_id: str,
        expected_sha256: str, now: datetime,
    ) -> None:
        """Requires a protected DB transaction for a consistent session check."""
        if not self.db.in_transaction:
            raise OperatorIdentityBlocked("canary_idp_atomic_check_required")
        current = _utc(now, "canary_idp_clock_invalid")
        if (not isinstance(token, str) or not 16 <= len(token) <= 4096
                or not isinstance(subject, str)
                or SAFE_NAME.fullmatch(subject) is None
                or not isinstance(expected_session_id, str)
                or SAFE_NAME.fullmatch(expected_session_id) is None
                or not isinstance(expected_sha256, str)
                or len(expected_sha256) != 64
                or any(c not in "0123456789abcdef" for c in expected_sha256)):
            raise OperatorIdentityBlocked("canary_idp_assertion_invalid")
        try:
            fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()
        except UnicodeEncodeError:
            raise OperatorIdentityBlocked("canary_idp_assertion_invalid") from None
        if fingerprint != expected_sha256:
            raise OperatorIdentityBlocked("canary_idp_assertion_unbound")
        parts = token.split(".")
        if len(parts) != 3:
            raise OperatorIdentityBlocked("canary_idp_assertion_invalid")
        a, b, c = parts
        try:
            header = _json_object(_unbase(a))
            claims = _json_object(_unbase(b))
            signature = _unbase(c)
        except Exception:
            raise OperatorIdentityBlocked("canary_idp_assertion_invalid") from None
        kid = header.get("kid")
        if (header.get("typ") != "JWT" or header.get("alg") != "RS256"
                or not isinstance(kid, str) or kid not in self.keys):
            raise OperatorIdentityBlocked("canary_idp_signature_invalid")
        try:
            self.keys[kid].verify(
                signature, (a+"."+b).encode("ascii"),
                padding.PKCS1v15(), hashes.SHA256(),
            )
        except (InvalidSignature, ValueError):
            raise OperatorIdentityBlocked("canary_idp_signature_invalid") from None
        if (claims.get("iss") != self.issuer
                or claims.get("aud") != AUDIENCE
                or claims.get("token_use") != TOKEN_USE
                or claims.get("scope") != SCOPE
                or claims.get("sub") != subject
                or claims.get("sid") != expected_session_id
                or claims.get("acr") != ACR):
            raise OperatorIdentityBlocked("canary_idp_claims_invalid")
        jti = claims.get("jti")
        if not isinstance(jti, str) or SAFE_NAME.fullmatch(jti) is None:
            raise OperatorIdentityBlocked("canary_idp_session_invalid")
        amr = claims.get("amr")
        if (not isinstance(amr, list) or len(amr) > 8
                or any(type(a) is not str for a in amr)
                or not {"mfa","webauthn"}.issubset(amr)):
            raise OperatorIdentityBlocked("canary_idp_phishing_resistant_mfa_required")
        try:
            iat, nbf, exp = (
                _epoch(claims,"iat"),_epoch(claims,"nbf"),_epoch(claims,"exp"),
            )
            auth_at, mfa_at = (
                _epoch(claims,"auth_time"),_epoch(claims,"mfa_at"),
            )
        except Exception:
            raise OperatorIdentityBlocked("canary_idp_time_invalid") from None
        seconds = current.timestamp()
        if (iat > seconds+30 or nbf > seconds+30
                or exp <= seconds or exp <= iat or exp-iat > 300
                or iat < seconds-300
                or auth_at > mfa_at or mfa_at > iat+30
                or mfa_at < iat-300 or mfa_at > seconds+30):
            raise OperatorIdentityBlocked("canary_idp_time_invalid")
        try:
            row = self.db.execute(
                """SELECT subject,issuer,signer_kid,token_jti,assertion_sha256,
                          authenticated_at,mfa_at,issued_at,expires_at,
                          authentication_profile,enabled,revoked_at
                   FROM sns_mirror_canary_idp_sessions WHERE session_id=?""",
                (expected_session_id,),
            ).fetchone()
        except sqlite3.Error:
            raise OperatorIdentityBlocked("canary_idp_registry_unavailable") from None
        if row != (
            subject,self.issuer,kid,jti,expected_sha256,auth_at,mfa_at,
            iat,exp,PROFILE,1,None,
        ):
            raise OperatorIdentityBlocked("canary_idp_session_not_active")
