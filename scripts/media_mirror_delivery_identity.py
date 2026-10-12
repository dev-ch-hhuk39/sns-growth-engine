#!/usr/bin/env python3
"""6J separately pinned, short-lived service identity for isolated reporting only.

Policies, target spreadsheet IDs and fixed row mappings MUST be provisioned
in the protected DB by trusted operations. Nothing from a client request can
grant an account, arbitrary spreadsheet, row number or publish permission.
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

from media_mirror_sheets_adapter import ReportingRowTarget
from media_review_trusted_precommit import _utc
from media_review_verified_identity import (
    SAFE_NAME, _epoch, _json_object, _unbase,
)

MIGRATION = (
    Path(__file__).resolve().parents[1] / "db" / "migrations"
    / "0010_sns_mirror_reporting_delivery.sql"
)
AUDIENCE = "sns-growth-mirror-reporting-write"
TOKEN_USE = "mirror_reporting_live"
SCOPE = "mirror:reporting:write"


class MirrorDeliveryBlocked(ValueError):
    """Sanitized code only; never JWT or provider data."""


def initialize_mirror_delivery_schema(db: sqlite3.Connection) -> None:
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise MirrorDeliveryBlocked("mirror_delivery_migration_requires_autocommit")
    try:
        for name in (
            "sns_media_mirror_outbox_heads",
            "sns_mirror_rehearsal_service_sessions",
        ):
            if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (name,),
            ).fetchone():
                raise MirrorDeliveryBlocked("mirror_delivery_prerequisite_missing")
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
        db.execute("PRAGMA foreign_keys=ON")
    except (sqlite3.Error, OSError):
        raise MirrorDeliveryBlocked("mirror_delivery_migration_failed") from None


class PinnedLiveMirrorServiceVerifier:
    """Dedicated service JWT + revoked session + pinned destination/row lookup.

    A *different* audience and scope from Phase 6I rehearsal and the media
    reviewer means neither legacy token can authorize a reporting write.
    """

    def __init__(
        self, *, db: sqlite3.Connection, issuer: str,
        public_keys_by_kid: Mapping[str, bytes],
    ) -> None:
        if (not isinstance(db, sqlite3.Connection) or not isinstance(issuer, str)
                or not issuer.startswith("https://")
                or not public_keys_by_kid):
            raise MirrorDeliveryBlocked("mirror_delivery_identity_config_invalid")
        keys: dict[str, rsa.RSAPublicKey] = {}
        try:
            for kid, pem in public_keys_by_kid.items():
                if not isinstance(kid, str) or SAFE_NAME.fullmatch(kid) is None:
                    raise MirrorDeliveryBlocked("mirror_delivery_key_untrusted")
                key = serialization.load_pem_public_key(pem)
                if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
                    raise MirrorDeliveryBlocked("mirror_delivery_key_untrusted")
                keys[kid] = key
        except (TypeError, ValueError):
            raise MirrorDeliveryBlocked("mirror_delivery_key_untrusted") from None
        self.db, self.issuer, self.keys = db, issuer, keys

    def verify(
        self, *, token: str, destination_id: str,
        account_id: str, slot_id: str, queue_id: str,
        now: datetime,
    ) -> tuple[str, ReportingRowTarget]:
        current = _utc(now, "mirror_delivery_clock_invalid")
        if not isinstance(token, str) or not 16 <= len(token) <= 4096:
            raise MirrorDeliveryBlocked("mirror_delivery_token_invalid")
        parts = token.split(".")
        if len(parts) != 3:
            raise MirrorDeliveryBlocked("mirror_delivery_token_invalid")
        a, b, c = parts
        try:
            header = _json_object(_unbase(a))
            claims = _json_object(_unbase(b))
            signature = _unbase(c)
        except Exception:
            raise MirrorDeliveryBlocked("mirror_delivery_token_invalid") from None
        kid = header.get("kid")
        if (header.get("typ") != "JWT" or header.get("alg") != "RS256"
                or not isinstance(kid, str) or kid not in self.keys):
            raise MirrorDeliveryBlocked("mirror_delivery_signature_invalid")
        try:
            self.keys[kid].verify(
                signature, (a+"."+b).encode("ascii"),
                padding.PKCS1v15(), hashes.SHA256(),
            )
        except (InvalidSignature, ValueError):
            raise MirrorDeliveryBlocked("mirror_delivery_signature_invalid") from None
        if (claims.get("iss") != self.issuer
                or claims.get("aud") != AUDIENCE
                or claims.get("token_use") != TOKEN_USE
                or claims.get("scope") != SCOPE):
            raise MirrorDeliveryBlocked("mirror_delivery_claims_invalid")
        subject, sid, jti = (
            claims.get("sub"), claims.get("sid"), claims.get("jti"),
        )
        if any(
            not isinstance(x, str) or SAFE_NAME.fullmatch(x) is None
            for x in (subject, sid, jti)
        ):
            raise MirrorDeliveryBlocked("mirror_delivery_subject_invalid")
        try:
            issued, not_before, expiry = (
                _epoch(claims, "iat"), _epoch(claims, "nbf"),
                _epoch(claims, "exp"),
            )
        except Exception:
            raise MirrorDeliveryBlocked("mirror_delivery_time_invalid") from None
        seconds = current.timestamp()
        if (issued > seconds + 30 or not_before > seconds + 30
                or expiry <= seconds or expiry <= issued
                or expiry - issued > 300):
            raise MirrorDeliveryBlocked("mirror_delivery_time_invalid")
        fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()
        try:
            session = self.db.execute(
                """SELECT subject,issuer,token_sha256,token_jti,
                          issued_at,expires_at,revoked_at,enabled
                   FROM sns_mirror_delivery_sessions WHERE session_id=?""",
                (sid,),
            ).fetchone()
            policy = self.db.execute(
                """SELECT account_id,service_subject,reporting_spreadsheet_id,
                          operational_spreadsheet_id,reporting_tab,mode,enabled
                   FROM sns_mirror_delivery_destinations WHERE destination_id=?""",
                (destination_id,),
            ).fetchone()
            mapping = self.db.execute(
                """SELECT row_number FROM sns_mirror_delivery_row_map
                   WHERE destination_id=? AND account_id=?
                     AND slot_id=? AND queue_id=?""",
                (destination_id,account_id,slot_id,queue_id),
            ).fetchone()
        except sqlite3.Error:
            raise MirrorDeliveryBlocked("mirror_delivery_identity_db_unavailable") from None
        if session is None or session != (
            subject, self.issuer, fingerprint, jti, issued, expiry, None, 1,
        ):
            raise MirrorDeliveryBlocked("mirror_delivery_session_not_active")
        if (policy is None or policy[0] != account_id or policy[1] != subject
                or policy[5:] != ("ISOLATED_REPORTING_ONLY",1)
                or mapping is None):
            raise MirrorDeliveryBlocked("mirror_delivery_policy_denied")
        target = ReportingRowTarget(
            reporting_spreadsheet_id=policy[2],
            operational_spreadsheet_id=policy[3],
            reporting_tab=policy[4],
            row_number=mapping[0],
        )
        try:
            target.validate()
        except Exception:
            raise MirrorDeliveryBlocked("mirror_delivery_target_untrusted") from None
        return subject, target
