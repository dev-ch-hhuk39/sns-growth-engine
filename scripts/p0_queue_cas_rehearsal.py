#!/usr/bin/env python3
"""SQLite P0 queue compare-and-swap rehearsal; NEVER real publish authority.

This local ledger protects synthetic observations from duplicate claims and
unknown-ACK replays. The operational publisher still uses legacy Sheets.
Neither this journal nor any returned value grants an API action, a ready
transition, or a migration permit. No live posting adapter imports this code.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MIGRATION = (
    Path(__file__).resolve().parents[1] / "db" / "migrations"
    / "0014_sns_p0_queue_cas_rehearsal.sql"
)
ACCOUNT_IDS = frozenset({"night_scout", "liver_manager"})
QUEUE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,120}\Z")
OP_RE = re.compile(r"p0_[A-Za-z0-9_-]{12,95}\Z")
HASH_RE = re.compile(r"[a-f0-9]{64}\Z")
ZERO = "0" * 64
SCHEMA = "sns_p0_queue_cas_rehearsal_event_v1"
OBSERVATION_FRESHNESS = timedelta(seconds=90)
FIELDS = frozenset({
    "schema_version", "operation_id", "account_id", "queue_id",
    "platform", "source_sha256", "observed_at", "version",
    "state", "action", "reason", "occurred_at", "previous_event_sha256",
})
STATES = {
    "OBSERVE": "OBSERVED_BLOCKED",
    "CLAIM": "CLAIMED_BLOCKED",
    "UNCERTAIN": "OUTCOME_UNKNOWN_BLOCKED",
    "CANCEL": "CANCELLED_BLOCKED",
}
HEAD_FIELDS = (
    "queue_id", "account_id", "platform", "source_sha256", "observed_at",
    "version", "state", "last_event_sha256", "updated_at",
)
SAFE_REASONS = frozenset({
    "DRY_RUN_REHEARSAL", "ACK_UNKNOWN", "LOCAL_PERSISTENCE_UNKNOWN",
    "CONCURRENT_SOURCE_CHANGE", "OPERATOR_CANCELLED",
})


class P0RehearsalBlocked(ValueError):
    """Errors contain only static reason codes, no source or credentials."""


def _json(obj: dict[str, Any]) -> str:
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=True, separators=(",", ":"),
        allow_nan=False,
    )


def _hash(event: dict[str, Any]) -> str:
    return hashlib.sha256(_json(event).encode("ascii")).hexdigest()


def _time(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise P0RehearsalBlocked("P0_TIME_UNTRUSTED")
    return value.astimezone(timezone.utc)


def _parse_time(value: str) -> datetime:
    try:
        return _time(datetime.fromisoformat(value))
    except (ValueError, TypeError, AttributeError):
        raise P0RehearsalBlocked("P0_TIME_UNTRUSTED") from None


def initialize_rehearsal_schema(
    db: sqlite3.Connection, *, explicit_local_test_only: bool = False,
) -> None:
    """Schema migration must be requested explicitly for synthetic testing."""
    if not explicit_local_test_only or not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise P0RehearsalBlocked("P0_LOCAL_MIGRATION_NOT_AUTHORIZED")
    try:
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
    except (OSError, sqlite3.Error):
        raise P0RehearsalBlocked("P0_LOCAL_MIGRATION_FAILED") from None


def _database(db: sqlite3.Connection) -> None:
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise P0RehearsalBlocked("P0_DATABASE_UNAVAILABLE")
    try:
        if db.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise P0RehearsalBlocked("P0_DATABASE_FOREIGN_KEYS_OFF")
        required = {
            "sns_p0_rehearsal_heads", "sns_p0_rehearsal_events",
        }
        present = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'",
        )}
        if not required.issubset(present):
            raise P0RehearsalBlocked("P0_SCHEMA_MISSING")
    except sqlite3.Error:
        raise P0RehearsalBlocked("P0_DATABASE_UNAVAILABLE") from None


def _head(db: sqlite3.Connection, queue_id: str) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT " + ",".join(HEAD_FIELDS)
        + " FROM sns_p0_rehearsal_heads WHERE queue_id=?",
        (queue_id,),
    ).fetchone()
    return dict(zip(HEAD_FIELDS, row)) if row else None


def _audit(db: sqlite3.Connection, queue_id: str, head: dict[str, Any] | None) -> None:
    rows = db.execute(
        """SELECT operation_id,version,action,previous_event_sha256,
                  event_sha256,payload_json FROM sns_p0_rehearsal_events
           WHERE queue_id=? ORDER BY version""",
        (queue_id,),
    ).fetchall()
    if head is None:
        if rows:
            raise P0RehearsalBlocked("P0_ORPHAN_JOURNAL")
        return
    if not rows or len(rows) != head["version"] or len(rows) > 4:
        raise P0RehearsalBlocked("P0_JOURNAL_LENGTH_INVALID")
    prior = ZERO
    previous_state = ""
    last: dict[str, Any] = {}
    for seq, (operation, version, action, previous, digest, encoded) in enumerate(rows, 1):
        try:
            event = json.loads(encoded)
        except (ValueError, TypeError):
            raise P0RehearsalBlocked("P0_JOURNAL_CORRUPT") from None
        expected_state = (
            STATES["OBSERVE"] if seq == 1 and action == "OBSERVE"
            else STATES["CLAIM"] if previous_state == STATES["OBSERVE"] and action == "CLAIM"
            else STATES["CANCEL"] if previous_state == STATES["OBSERVE"] and action == "CANCEL"
            else STATES["UNCERTAIN"] if previous_state == STATES["CLAIM"] and action == "UNCERTAIN"
            else None
        )
        if (not isinstance(event, dict) or set(event) != FIELDS
                or event["schema_version"] != SCHEMA
                or event["operation_id"] != operation
                or event["queue_id"] != queue_id
                or event["version"] != seq or seq != version
                or event["action"] != action
                or event["state"] != expected_state or expected_state is None
                or event["previous_event_sha256"] != prior
                or previous != prior or digest != _hash(event)):
            raise P0RehearsalBlocked("P0_JOURNAL_TAMPERED")
        if seq > 1 and any(
            event[field] != last[field]
            for field in ("account_id", "queue_id", "platform", "source_sha256", "observed_at")
        ):
            raise P0RehearsalBlocked("P0_JOURNAL_IDENTITY_CHANGED")
        previous_state, prior, last = expected_state, digest, event
    for field in HEAD_FIELDS:
        expected = (
            prior if field == "last_event_sha256"
            else last["occurred_at"] if field == "updated_at"
            else last[field]
        )
        if head[field] != expected:
            raise P0RehearsalBlocked("P0_HEAD_TAMPERED")


def _safe_result(head: dict[str, Any]) -> dict[str, Any]:
    identity = hashlib.sha256(
        (head["account_id"] + ":" + head["queue_id"]).encode("utf-8"),
    ).hexdigest()[:20]
    return {
        "status": head["state"], "identity_hash": identity,
        "revision": head["version"],
        "head_sha256": head["last_event_sha256"],
        "publish_authorized": False, "dispatch_allowed": False,
        "sheets_write_allowed": False, "source_cutover_authorized": False,
        "network_called": False,
    }


class P0QueueRehearsal:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def inspect(self, *, queue_id: str) -> dict[str, Any]:
        _database(self.db)
        if not isinstance(queue_id, str) or not QUEUE_RE.fullmatch(queue_id):
            raise P0RehearsalBlocked("P0_QUEUE_ID_INVALID")
        head = _head(self.db, queue_id)
        _audit(self.db, queue_id, head)
        if not head:
            raise P0RehearsalBlocked("P0_QUEUE_NOT_OBSERVED")
        return _safe_result(head)

    def observe(
        self, *, account_id: str, queue_id: str, platform: str,
        source_sha256: str, observed_at: datetime,
        operation_id: str, as_of: datetime,
    ) -> dict[str, Any]:
        return self._transition(
            "OBSERVE", account_id=account_id, queue_id=queue_id,
            operation_id=operation_id, as_of=as_of,
            observed_at=observed_at, source_sha256=source_sha256,
            platform=platform,
        )

    def claim(
        self, *, account_id: str, queue_id: str, operation_id: str,
        expected_revision: int, expected_head_sha256: str,
        expected_source_sha256: str, as_of: datetime,
    ) -> dict[str, Any]:
        return self._transition(
            "CLAIM", account_id=account_id, queue_id=queue_id,
            operation_id=operation_id, as_of=as_of,
            expected_revision=expected_revision, expected_head_sha256=expected_head_sha256,
            expected_source_sha256=expected_source_sha256,
        )

    def quarantine(
        self, *, account_id: str, queue_id: str, operation_id: str,
        expected_revision: int, expected_head_sha256: str, reason: str,
        as_of: datetime,
    ) -> dict[str, Any]:
        return self._transition(
            "UNCERTAIN", account_id=account_id, queue_id=queue_id,
            operation_id=operation_id, as_of=as_of, reason=reason,
            expected_revision=expected_revision, expected_head_sha256=expected_head_sha256,
        )

    def cancel_unclaimed(
        self, *, account_id: str, queue_id: str, operation_id: str,
        expected_revision: int, expected_head_sha256: str,
        as_of: datetime,
    ) -> dict[str, Any]:
        return self._transition(
            "CANCEL", account_id=account_id, queue_id=queue_id,
            operation_id=operation_id, as_of=as_of,
            expected_revision=expected_revision, expected_head_sha256=expected_head_sha256,
        )

    def _transition(
        self, action: str, *, account_id: str, queue_id: str,
        operation_id: str, as_of: datetime,
        platform: str = "threads", source_sha256: str = "",
        observed_at: datetime | None = None,
        expected_revision: int | None = None,
        expected_head_sha256: str = "", expected_source_sha256: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        _database(self.db)
        if (type(account_id) is not str or account_id not in ACCOUNT_IDS
                or type(platform) is not str or platform != "threads"
                or type(queue_id) is not str or not QUEUE_RE.fullmatch(queue_id)
                or type(operation_id) is not str or not OP_RE.fullmatch(operation_id)):
            raise P0RehearsalBlocked("P0_INVALID_SCOPE_OR_OPERATION")
        now = _time(as_of)
        if action == "OBSERVE":
            if (type(source_sha256) is not str or not HASH_RE.fullmatch(source_sha256)
                    or observed_at is None):
                raise P0RehearsalBlocked("P0_SOURCE_PROOF_INVALID")
            observed = _time(observed_at)
            if not timedelta(0) <= now - observed <= OBSERVATION_FRESHNESS:
                raise P0RehearsalBlocked("P0_SOURCE_STALE_OR_IN_FUTURE")
        else:
            if (type(expected_revision) is not int or expected_revision < 1
                    or type(expected_head_sha256) is not str
                    or not HASH_RE.fullmatch(expected_head_sha256)):
                raise P0RehearsalBlocked("P0_EXPECTED_CAS_INVALID")
            if action == "CLAIM" and (
                type(expected_source_sha256) is not str
                or not HASH_RE.fullmatch(expected_source_sha256)
            ):
                raise P0RehearsalBlocked("P0_SOURCE_PROOF_INVALID")
            if action == "UNCERTAIN" and reason not in SAFE_REASONS:
                raise P0RehearsalBlocked("P0_REASON_INVALID")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            old = _head(self.db, queue_id)
            _audit(self.db, queue_id, old)
            if action == "OBSERVE":
                if old:
                    raise P0RehearsalBlocked("P0_GLOBAL_QUEUE_ID_ALREADY_USED")
                revision, previous = 1, ZERO
                observed_iso = observed.isoformat()
                sha = source_sha256
            else:
                if not old:
                    raise P0RehearsalBlocked("P0_QUEUE_NOT_OBSERVED")
                if old["account_id"] != account_id:
                    raise P0RehearsalBlocked("P0_ACCOUNT_SCOPE_MISMATCH")
                if (old["version"] != expected_revision
                        or old["last_event_sha256"] != expected_head_sha256):
                    raise P0RehearsalBlocked("P0_CAS_STALE")
                if action == "CLAIM" and old["source_sha256"] != expected_source_sha256:
                    raise P0RehearsalBlocked("P0_SOURCE_HASH_CHANGED")
                if action == "CLAIM" and (
                    not timedelta(0) <= now - _parse_time(old["observed_at"])
                    <= OBSERVATION_FRESHNESS
                ):
                    raise P0RehearsalBlocked("P0_SOURCE_EXPIRED_NO_REPLAY")
                previous_state = old["state"]
                allowed = (
                    (previous_state == STATES["OBSERVE"] and action in {"CLAIM", "CANCEL"})
                    or (previous_state == STATES["CLAIM"] and action == "UNCERTAIN")
                )
                if not allowed:
                    raise P0RehearsalBlocked("P0_REPLAY_OR_TERMINAL_STATE")
                revision, previous = old["version"] + 1, old["last_event_sha256"]
                observed_iso, sha = old["observed_at"], old["source_sha256"]
            state = STATES[action]
            event = {
                "schema_version": SCHEMA, "operation_id": operation_id,
                "account_id": account_id, "queue_id": queue_id,
                "platform": "threads", "source_sha256": sha,
                "observed_at": observed_iso, "version": revision,
                "state": state, "action": action,
                "reason": reason if action == "UNCERTAIN" else "",
                "occurred_at": now.isoformat(),
                "previous_event_sha256": previous,
            }
            digest = _hash(event)
            if old is None:
                self.db.execute(
                    """INSERT INTO sns_p0_rehearsal_heads
                       (queue_id,account_id,platform,source_sha256,observed_at,
                        version,state,last_event_sha256,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?)""",
                    (queue_id, account_id, "threads", sha, observed_iso,
                     revision, state, digest, event["occurred_at"]),
                )
            else:
                updated = self.db.execute(
                    """UPDATE sns_p0_rehearsal_heads
                       SET version=?,state=?,last_event_sha256=?,updated_at=?
                       WHERE queue_id=? AND account_id=? AND version=?
                       AND last_event_sha256=?""",
                    (revision, state, digest, event["occurred_at"], queue_id,
                     account_id, old["version"], previous),
                )
                if updated.rowcount != 1:
                    raise P0RehearsalBlocked("P0_CAS_CONFLICT")
            self.db.execute(
                """INSERT INTO sns_p0_rehearsal_events
                   (operation_id,queue_id,version,action,previous_event_sha256,
                    event_sha256,payload_json)
                   VALUES(?,?,?,?,?,?,?)""",
                (operation_id, queue_id, revision, action,
                 previous, digest, _json(event)),
            )
            self.db.execute("COMMIT")
            # Readback must match the committed state and intact event chain.
            saved = _head(self.db, queue_id)
            _audit(self.db, queue_id, saved)
            if not saved or saved["version"] != revision or saved["last_event_sha256"] != digest:
                raise P0RehearsalBlocked("P0_COMMIT_READBACK_UNKNOWN")
            return _safe_result(saved)
        except P0RehearsalBlocked:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise
        except sqlite3.Error:
            if self.db.in_transaction:
                self.db.execute("ROLLBACK")
            raise P0RehearsalBlocked("P0_SQLITE_OUTCOME_UNKNOWN_NO_REPLAY") from None

    def authorize_external_post(self, **_ignored: Any) -> None:
        raise P0RehearsalBlocked("P0_REHEARSAL_CAN_NEVER_AUTHORIZE_POST")
