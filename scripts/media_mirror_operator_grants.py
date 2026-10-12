#!/usr/bin/env python3
"""6O default-deny current human grants for a single reporting canary.

The registry is server provisioned, never populated from JWTs, Google Sheets,
client messages or environment auto-discovery. A revoked / expired / disabled
grant cannot be overridden by a cryptographically valid operator signature.
This is a code-only prerequisite, NOT real provider/IdP approval evidence.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parents[1] / "db" / "migrations"
    / "0012_sns_canary_operator_grants.sql"
)


class OperatorGrantBlocked(ValueError):
    """Stable and sanitized denial; never show credentials or signer contents."""


def initialize_operator_grant_schema(db: sqlite3.Connection) -> None:
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise OperatorGrantBlocked("operator_grant_migration_requires_autocommit")
    try:
        for table in (
            "sns_mirror_canary_signoff_uses",
            "sns_mirror_delivery_destinations",
        ):
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone() is None:
                raise OperatorGrantBlocked("operator_grant_migration_prerequisite_missing")
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
        db.execute("PRAGMA foreign_keys=ON")
    except (sqlite3.Error, OSError):
        raise OperatorGrantBlocked("operator_grant_migration_failed") from None


def require_current_operator_grant(
    db: sqlite3.Connection, *, kid: str, subject: str, account_id: str,
    destination_id: str, approval_slot: int, grant_generation: int,
    issued_at: int, expires_at: int, now_seconds: int,
) -> None:
    """Fail-closed lookup inside the same transaction as use+PREPARE.

    A new generation is required for a disabled/revoked->enabled grant.
    Caller checks pinned signing key material and distinct human subjects.
    """
    if not isinstance(db, sqlite3.Connection) or not db.in_transaction:
        raise OperatorGrantBlocked("operator_grant_atomic_check_required")
    if (type(approval_slot) is not int
            or approval_slot not in (1, 2)
            or type(grant_generation) is not int
            or not 1 <= grant_generation <= 2147483647
            or any(type(t) is not int for t in (
                issued_at, expires_at, now_seconds,
            ))
            or any(not isinstance(v, str) or not v for v in (
                kid, subject, account_id, destination_id,
            ))):
        raise OperatorGrantBlocked("operator_grant_identifier_invalid")
    try:
        rows = db.execute(
            """SELECT signer_subject,grant_generation,valid_from,valid_until,
                      enabled,revoked_at
               FROM sns_mirror_canary_operator_grants
               WHERE signer_kid=? AND account_id=?
                 AND destination_id=? AND approval_slot=?""",
            (kid,account_id,destination_id,approval_slot),
        ).fetchall()
    except sqlite3.Error:
        raise OperatorGrantBlocked("operator_grant_registry_unavailable") from None
    if len(rows) != 1:
        raise OperatorGrantBlocked("operator_grant_missing")
    pinned_subject,version,valid_from,valid_until,enabled,revoked_at = rows[0]
    if (pinned_subject != subject
            or version != grant_generation
            or enabled != 1 or revoked_at is not None
            or not valid_from <= issued_at <= now_seconds < valid_until
            or not issued_at < expires_at <= valid_until):
        raise OperatorGrantBlocked("operator_grant_not_current")
