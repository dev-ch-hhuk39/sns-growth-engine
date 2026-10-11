#!/usr/bin/env python3
"""Phase 5B-5B: pinned RS256 identity + server-provisioned session/role authority.

A trusted IdP callback must provision sessions and role grants. This module
does NOT create logins, bootstrap grants, serve an endpoint or enable publishing.
Never accept a signing key, issuer, session row or role assignment from a request.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from media_review_trusted_precommit import EXPECTED_AUDIENCE, VerifiedReviewer

SAFE_NAME = re.compile(r"[A-Za-z0-9_.:-]{8,128}\Z")
B64URL = re.compile(r"[A-Za-z0-9_-]+\Z")
MAX_TOKEN_LENGTH = 4096


class IdentityBlocked(ValueError):
    """Sanitized error code only, with no bearer token or provider response."""


def _json_object(raw: bytes) -> dict[str, Any]:
    if len(raw) > 3000:
        raise IdentityBlocked("jwt_payload_invalid")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in pairs:
            if key in obj:
                raise IdentityBlocked("jwt_duplicate_claim")
            obj[key] = value
        return obj

    try:
        parsed = json.loads(
            raw, object_pairs_hook=unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (ValueError, UnicodeDecodeError):
        raise IdentityBlocked("jwt_payload_invalid") from None
    if not isinstance(parsed, dict):
        raise IdentityBlocked("jwt_payload_invalid")
    return parsed


def _unbase(part: str) -> bytes:
    if not part or len(part) > 4096 or B64URL.fullmatch(part) is None:
        raise IdentityBlocked("jwt_format_invalid")
    try:
        return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))
    except (ValueError, base64.binascii.Error):
        raise IdentityBlocked("jwt_format_invalid") from None


def _epoch(claims: dict[str, Any], key: str) -> int:
    value = claims.get(key)
    if type(value) is not int or value <= 0 or value > 4102444800:
        raise IdentityBlocked("jwt_time_invalid")
    return value


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise IdentityBlocked("identity_clock_invalid")
    return value.astimezone(timezone.utc)


class SQLiteSessionAuthority:
    """Read-only access to sessions/grants created by an independent trusted IdP handler."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        if not isinstance(connection, sqlite3.Connection):
            raise IdentityBlocked("session_store_not_configured")
        self.connection = connection

    def principal_for(
        self, *, sid: str, subject: str, jti: str, token_fingerprint: str,
        issuer: str, auth_time: int, mfa_time: int, expiry: int, now: datetime,
    ) -> VerifiedReviewer:
        try:
            row = self.connection.execute(
                """SELECT subject,issuer,token_sha256,token_jti,
                          authenticated_at,mfa_at,expires_at,revoked_at
                   FROM sns_review_sessions WHERE session_id=?""", (sid,),
            ).fetchone()
            if (row is None or row[:7] != (
                    subject, issuer, token_fingerprint, jti, auth_time,
                    mfa_time, expiry,
                ) or row[7] is not None):
                raise IdentityBlocked("session_not_active")
            assignments = self.connection.execute(
                """SELECT account_id,role FROM sns_review_account_grants
                   WHERE subject=? AND enabled=1""", (subject,),
            ).fetchall()
        except sqlite3.Error:
            raise IdentityBlocked("session_store_unavailable") from None
        scopes = frozenset(
            acc for acc, role in assignments
            if role in {"ADMIN", "MEDIA_REVIEWER"}
        )
        roles = frozenset(role for _, role in assignments)
        if not scopes or not roles.intersection({"ADMIN", "MEDIA_REVIEWER"}):
            raise IdentityBlocked("reviewer_not_authorized")
        return VerifiedReviewer(
            subject=subject, roles=roles, account_scopes=scopes,
            issuer=issuer, audience=EXPECTED_AUDIENCE,
            authenticated_at=datetime.fromtimestamp(auth_time, tz=timezone.utc),
            mfa_at=datetime.fromtimestamp(mfa_time, tz=timezone.utc),
            expires_at=datetime.fromtimestamp(expiry, tz=timezone.utc),
        )


class PinnedRS256SessionVerifier:
    """Verifies a JWT against SERVER PINNED keys, then active session and RBAC.

    No remote JWK discovery, client-provided public keys, HS256, alg=none, or
    implicit admin permission. Unknown signing key IDs always fail closed.
    """

    def __init__(
        self, *, issuer: str, public_keys_by_kid: Mapping[str, bytes],
        sessions: SQLiteSessionAuthority, audience: str = EXPECTED_AUDIENCE,
    ) -> None:
        if (not isinstance(issuer, str) or not issuer.startswith("https://")
                or audience != EXPECTED_AUDIENCE or not public_keys_by_kid
                or not isinstance(sessions, SQLiteSessionAuthority)):
            raise IdentityBlocked("identity_configuration_invalid")
        keys: dict[str, rsa.RSAPublicKey] = {}
        try:
            for kid, pem in public_keys_by_kid.items():
                if not isinstance(kid, str) or not SAFE_NAME.fullmatch(kid):
                    raise IdentityBlocked("identity_key_invalid")
                public = serialization.load_pem_public_key(pem)
                if not isinstance(public, rsa.RSAPublicKey) or public.key_size < 2048:
                    raise IdentityBlocked("identity_key_invalid")
                keys[kid] = public
        except (TypeError, ValueError):
            raise IdentityBlocked("identity_key_invalid") from None
        self._keys = keys
        self._issuer = issuer
        self._sessions = sessions

    def verify(self, bearer_token: str, *, now: datetime) -> VerifiedReviewer:
        current = _utc(now)
        if (not isinstance(bearer_token, str)
                or not 16 <= len(bearer_token) <= MAX_TOKEN_LENGTH):
            raise IdentityBlocked("jwt_format_invalid")
        parts = bearer_token.split(".")
        if len(parts) != 3:
            raise IdentityBlocked("jwt_format_invalid")
        header_part, claims_part, signature_part = parts
        header = _json_object(_unbase(header_part))
        if header.get("alg") != "RS256" or header.get("typ") != "JWT":
            raise IdentityBlocked("jwt_algorithm_forbidden")
        kid = header.get("kid")
        if not isinstance(kid, str) or kid not in self._keys:
            raise IdentityBlocked("jwt_key_untrusted")
        signature = _unbase(signature_part)
        try:
            self._keys[kid].verify(
                signature, (header_part + "." + claims_part).encode("ascii"),
                padding.PKCS1v15(), hashes.SHA256(),
            )
        except (InvalidSignature, ValueError):
            raise IdentityBlocked("jwt_signature_invalid") from None
        claims = _json_object(_unbase(claims_part))
        if (claims.get("iss") != self._issuer
                or claims.get("aud") != EXPECTED_AUDIENCE):
            raise IdentityBlocked("jwt_issuer_or_audience_invalid")
        subject, sid, jti = (
            claims.get("sub"), claims.get("sid"), claims.get("jti"),
        )
        if any(not isinstance(x, str) or not SAFE_NAME.fullmatch(x)
               for x in (subject, sid, jti)):
            raise IdentityBlocked("jwt_subject_or_session_invalid")
        amr = claims.get("amr")
        if not isinstance(amr, list) or "mfa" not in amr or any(
            not isinstance(x, str) for x in amr
        ):
            raise IdentityBlocked("jwt_mfa_required")
        issued, not_before, expiry = (
            _epoch(claims, "iat"), _epoch(claims, "nbf"), _epoch(claims, "exp"),
        )
        auth_time, mfa_time = (
            _epoch(claims, "auth_time"), _epoch(claims, "mfa_at"),
        )
        now_ts = current.timestamp()
        if (issued > now_ts + 120 or not_before > now_ts + 120
                or expiry <= now_ts or expiry <= issued
                or expiry - issued > 8 * 3600
                or auth_time > issued + 120 or mfa_time < auth_time
                or mfa_time > issued + 120
                or mfa_time > now_ts + 120):
            raise IdentityBlocked("jwt_time_invalid")
        fingerprint = hashlib.sha256(bearer_token.encode("ascii")).hexdigest()
        return self._sessions.principal_for(
            sid=sid, subject=subject, jti=jti,
            token_fingerprint=fingerprint, issuer=self._issuer,
            auth_time=auth_time, mfa_time=mfa_time, expiry=expiry, now=current,
        )
