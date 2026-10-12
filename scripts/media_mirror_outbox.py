#!/usr/bin/env python3
"""Phase 5B-6G: durable local *planning* outbox, no Google Sheets transport.

The reviewed queue is still operationally backed by an external spreadsheet.
This outbox atomically records each new managed-queue preview (if migration
0008 is installed), rejects stale versions and prevents ambiguous automatic
retries. A CLAIMED_BLOCKED record is not a delivery authorization or ACK.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from media_publish_intent_authority import _actor, _database
from media_review_trusted_precommit import _utc
from media_review_verified_identity import PinnedRS256SessionVerifier

MIGRATION = (Path(__file__).resolve().parents[1] / "db" / "migrations"
             / "0008_sns_media_mirror_outbox.sql")
ZERO = "0" * 64
SHA = re.compile(r"[0-9a-f]{64}\Z")
OP = re.compile(r"mirror_[A-Za-z0-9_.:-]{12,110}\Z")
SCHEMA = "sns_media_mirror_outbox_event_v1"
HEAD_FIELDS = (
    "account_id", "slot_id", "queue_id", "writer_version",
    "projection_sha256", "version", "state", "lease_expires_at",
    "last_event_sha256", "updated_at",
)
EVENT_FIELDS = frozenset((
    "schema_version", "operation_id", "event_sha256", "account_id",
    "slot_id", "queue_id", "writer_version", "projection_sha256",
    "version", "state", "action", "lease_expires_at",
    "actor", "reason", "created_at", "previous_event_sha256",
))
STATES = {
    "ENQUEUE": "QUEUED_BLOCKED",
    "CLAIM": "CLAIMED_BLOCKED",
    "UNCERTAIN": "UNCERTAIN_BLOCKED",
    "SUPERSEDE": "SUPERSEDED_BLOCKED",
    "CANCEL": "CANCELLED_BLOCKED",
}
MAX_EVENTS = 64
CLAIM_WINDOW = timedelta(seconds=45)


class MirrorOutboxBlocked(ValueError):
    """Only reason codes; never include private queue text or auth tokens."""


def initialize_mirror_outbox_schema(db: sqlite3.Connection) -> None:
    """Manual trusted migration, never bootstrapped by a request."""
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise MirrorOutboxBlocked("mirror_schema_requires_autocommit")
    try:
        for table in ("sns_media_managed_queue_heads",
                      "sns_media_sheet_mirror_previews"):
            if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone():
                raise MirrorOutboxBlocked("mirror_missing_managed_schema")
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
        db.execute("PRAGMA foreign_keys=ON")
    except (sqlite3.Error, OSError):
        raise MirrorOutboxBlocked("mirror_migration_failed") from None


def _canon(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canon(value).encode("ascii")).hexdigest()


def _head(db: sqlite3.Connection, event_id: str) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT " + ",".join(HEAD_FIELDS) + """
         FROM sns_media_mirror_outbox_heads WHERE event_sha256=?""",
        (event_id,),
    ).fetchone()
    return dict(zip(HEAD_FIELDS, row)) if row else None


def _audit(
    db: sqlite3.Connection, event_id: str, head: dict[str, Any] | None,
) -> None:
    rows = db.execute(
        """SELECT version,action,operation_id,previous_event_sha256,
                  journal_sha256,payload_json
           FROM sns_media_mirror_outbox_events
           WHERE event_sha256=? ORDER BY version""",
        (event_id,),
    ).fetchall()
    if head is None:
        if rows:
            raise MirrorOutboxBlocked("mirror_orphan_history")
        return
    if not rows or len(rows) != head["version"] or len(rows) > MAX_EVENTS:
        raise MirrorOutboxBlocked("mirror_history_invalid")
    previous = ZERO
    current_state = ""
    final = None
    for number, (version, action, operation, prev, digest, raw) in enumerate(rows, 1):
        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            raise MirrorOutboxBlocked("mirror_history_corrupt") from None
        if (not isinstance(event, dict) or set(event) != EVENT_FIELDS
                or event["schema_version"] != SCHEMA
                or event["version"] != number or version != number
                or event["action"] != action or event["operation_id"] != operation
                or event["event_sha256"] != event_id
                or prev != previous or event["previous_event_sha256"] != prev
                or digest != _hash(event)):
            raise MirrorOutboxBlocked("mirror_history_tampered")
        expected = (
            "QUEUED_BLOCKED" if number == 1 and action == "ENQUEUE"
            else "CLAIMED_BLOCKED"
            if current_state == "QUEUED_BLOCKED" and action == "CLAIM"
            else "SUPERSEDED_BLOCKED"
            if current_state == "QUEUED_BLOCKED" and action == "SUPERSEDE"
            else "CANCELLED_BLOCKED"
            if current_state in ("QUEUED_BLOCKED", "CLAIMED_BLOCKED")
            and action == "CANCEL"
            else "UNCERTAIN_BLOCKED"
            if current_state == "CLAIMED_BLOCKED" and action == "UNCERTAIN"
            else None
        )
        if event["state"] != expected or expected is None:
            raise MirrorOutboxBlocked("mirror_transition_tampered")
        if final is not None and any(
            event[field] != final[field] for field in (
                "account_id", "slot_id", "queue_id", "writer_version",
                "projection_sha256",
            )
        ):
            raise MirrorOutboxBlocked("mirror_identity_tampered")
        if (action != "CLAIM" and final is not None
                and event["lease_expires_at"] != final["lease_expires_at"]):
            raise MirrorOutboxBlocked("mirror_lease_tampered")
        current_state, previous, final = expected, digest, event
    assert final is not None
    for name in HEAD_FIELDS:
        expected = (previous if name == "last_event_sha256"
                    else final["created_at"] if name == "updated_at"
                    else final[name])
        if head[name] != expected:
            raise MirrorOutboxBlocked("mirror_head_tampered")


def _result(state: str, version: int, digest: str,
            *, projection: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {
        "status": state, "outbox_version": version,
        "audit_sha256": digest,
        "sync_executed": False, "mirror_confirmed": False,
        "publish_authorized": False, "dispatch_allowed": False,
        "sheets_write_allowed": False, "ready_transitions_performed": False,
    }
    if projection is not None:
        result["mirror_preview"] = projection
    return result


def _write(
    db: sqlite3.Connection, event_id: str,
    *, old: dict[str, Any] | None, action: str, operation_id: str,
    key: tuple[str, str, str], writer_version: int, projection_sha256: str,
    actor: str, reason: str, now: datetime, lease_expires_at: str | None,
) -> dict[str, Any]:
    version = 1 if old is None else old["version"] + 1
    if version > MAX_EVENTS:
        raise MirrorOutboxBlocked("mirror_history_at_capacity")
    state = STATES[action]
    event = {
        "schema_version": SCHEMA, "operation_id": operation_id,
        "event_sha256": event_id,
        "account_id": key[0], "slot_id": key[1], "queue_id": key[2],
        "writer_version": writer_version,
        "projection_sha256": projection_sha256,
        "version": version, "state": state, "action": action,
        "lease_expires_at": lease_expires_at,
        "actor": actor, "reason": reason,
        "created_at": now.isoformat(timespec="seconds"),
        "previous_event_sha256": old["last_event_sha256"] if old else ZERO,
    }
    digest = _hash(event)
    if old is None:
        db.execute(
            """INSERT INTO sns_media_mirror_outbox_heads (
                event_sha256,account_id,slot_id,queue_id,writer_version,
                projection_sha256,version,state,lease_expires_at,
                last_event_sha256,updated_at
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (event_id, *key, writer_version, projection_sha256,
             version, state, lease_expires_at, digest, event["created_at"]),
        )
    else:
        changed = db.execute(
            """UPDATE sns_media_mirror_outbox_heads SET
                 version=?,state=?,lease_expires_at=?,
                 last_event_sha256=?,updated_at=?
               WHERE event_sha256=? AND version=? AND last_event_sha256=?""",
            (version, state, lease_expires_at, digest, event["created_at"],
             event_id, old["version"], old["last_event_sha256"]),
        )
        if changed.rowcount != 1:
            raise MirrorOutboxBlocked("mirror_concurrent_change")
    db.execute(
        """INSERT INTO sns_media_mirror_outbox_events(
             operation_id,event_sha256,version,action,previous_event_sha256,
             journal_sha256,payload_json
           ) VALUES (?,?,?,?,?,?,?)""",
        (operation_id, event_id, version, action,
         event["previous_event_sha256"], digest, _canon(event)),
    )
    return _result(state, version, digest)


def enqueue_in_managed_write(
    db: sqlite3.Connection, *, event_id: str, key: tuple[str, str, str],
    writer_version: int, projection_sha256: str, now: datetime,
) -> None:
    """Called *inside* existing authenticated managed-writer transaction.

    Legacy DBs without migration 0008 remain unaffected. If 0008 exists,
    corrupt/duplicate outbox operations fail the *whole* managed write;
    never silently lose a managed preview after migration.
    """
    installed = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' "
        "AND name='sns_media_mirror_outbox_heads'"
    ).fetchone()
    if not installed:
        return
    if not SHA.fullmatch(event_id) or not SHA.fullmatch(projection_sha256):
        raise MirrorOutboxBlocked("mirror_preview_digest_invalid")
    if not db.in_transaction:
        raise MirrorOutboxBlocked("mirror_enqueue_needs_writer_transaction")
    _write(
        db, event_id, old=None, action="ENQUEUE",
        operation_id="mirror_enqueue_" + event_id[:56], key=key,
        writer_version=writer_version, projection_sha256=projection_sha256,
        actor="trusted_managed_writer", reason="managed_queue_event",
        now=now, lease_expires_at=None,
    )


def _projection_for(
    db: sqlite3.Connection, event_id: str,
    head: dict[str, Any],
) -> dict[str, Any]:
    """Only the exact immutable latest, safe, view-only projection."""
    from media_managed_queue_writer import (
        _history as _writer_history, _projection as _expected_projection,
        _hash as _writer_hash, _row as _writer_head,
    )
    key = (head["account_id"], head["slot_id"], head["queue_id"])
    writer = _writer_head(db, key)
    _writer_history(db, key, writer)
    if (writer is None or writer["last_event_sha256"] != event_id
            or writer["version"] != head["writer_version"]):
        raise MirrorOutboxBlocked("mirror_writer_superseded")
    stored = db.execute(
        """SELECT projection_sha256,projection_json
           FROM sns_media_sheet_mirror_previews WHERE event_sha256=?""",
        (event_id,),
    ).fetchone()
    if not stored:
        raise MirrorOutboxBlocked("mirror_projection_missing")
    try:
        projection = json.loads(stored[1])
    except (ValueError, TypeError):
        raise MirrorOutboxBlocked("mirror_projection_corrupt") from None
    if (not isinstance(projection, dict)
            or stored[0] != head["projection_sha256"]
            or _writer_hash(projection) != stored[0]
            or projection != _expected_projection(
                key, version=writer["version"], state=writer["state"],
                digest=event_id, shadow_sha=writer["shadow_event_sha256"],
                queue_sha=writer["queue_sha256"],
            )
            or projection.get("view_only") is not True
            or projection.get("publish_authorized") is not False):
        raise MirrorOutboxBlocked("mirror_projection_tampered")
    return projection


class MirrorOutbox:
    """Authenticated human staging only; transport and service identity absent."""

    def __init__(self, db: sqlite3.Connection):
        if not isinstance(db, sqlite3.Connection):
            raise MirrorOutboxBlocked("mirror_database_invalid")
        self.db = db

    def claim_preview(
        self, *, event_sha256: str, operation_id: str,
        expected_outbox_version: int, expected_head_sha256: str,
        verifier: PinnedRS256SessionVerifier | None, bearer: str,
        trusted_issuer: str, as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Review operator claims a preview for OFFLINE inspection, NOT delivery."""
        _database(self.db)
        if (not isinstance(event_sha256, str) or not SHA.fullmatch(event_sha256)
                or not isinstance(operation_id, str) or not OP.fullmatch(operation_id)
                or type(expected_outbox_version) is not int
                or not isinstance(expected_head_sha256, str)):
            raise MirrorOutboxBlocked("mirror_claim_arguments_invalid")
        now = _utc(as_of or datetime.now(timezone.utc), "mirror_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            head = _head(self.db, event_sha256)
            _audit(self.db, event_sha256, head)
            if (not head or head["version"] != expected_outbox_version
                    or head["last_event_sha256"] != expected_head_sha256
                    or head["state"] != "QUEUED_BLOCKED"):
                raise MirrorOutboxBlocked("mirror_claim_conflict")
            key = (head["account_id"], head["slot_id"], head["queue_id"])
            actor = _actor(
                self.db, verifier=verifier, bearer=bearer,
                issuer=trusted_issuer, key=key, now=now,
            )
            try:
                projection = _projection_for(self.db, event_sha256, head)
            except MirrorOutboxBlocked as exc:
                if str(exc) != "mirror_writer_superseded":
                    raise
                result = _write(
                    self.db, event_sha256, old=head, action="SUPERSEDE",
                    operation_id=operation_id, key=key,
                    writer_version=head["writer_version"],
                    projection_sha256=head["projection_sha256"], actor=actor,
                    reason="newer_writer_version", now=now, lease_expires_at=None,
                )
                self.db.commit()
                return result
            until = (now + CLAIM_WINDOW).isoformat(timespec="seconds")
            result = _write(
                self.db, event_sha256, old=head, action="CLAIM",
                operation_id=operation_id, key=key,
                writer_version=head["writer_version"],
                projection_sha256=head["projection_sha256"], actor=actor,
                reason="offline_preview_only", now=now,
                lease_expires_at=until,
            )
            self.db.commit()
            result["mirror_preview"] = projection
            result["claim_expires_at"] = until
            return result
        except MirrorOutboxBlocked:
            self.db.rollback()
            raise
        except sqlite3.IntegrityError:
            self.db.rollback()
            raise MirrorOutboxBlocked("mirror_duplicate_or_replay") from None
        except Exception:
            self.db.rollback()
            raise MirrorOutboxBlocked("mirror_claim_failed") from None

    def stop(
        self, *, event_sha256: str, operation_id: str,
        expected_outbox_version: int, expected_head_sha256: str,
        action: str, verifier: PinnedRS256SessionVerifier | None,
        bearer: str, trusted_issuer: str,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Mark ambiguous manual outcome UNCERTAIN; no automatic retries."""
        _database(self.db)
        if (not isinstance(event_sha256, str) or not SHA.fullmatch(event_sha256)
                or not isinstance(operation_id, str) or not OP.fullmatch(operation_id)
                or action not in ("CANCEL", "UNCERTAIN")
                or type(expected_outbox_version) is not int
                or not isinstance(expected_head_sha256, str)):
            raise MirrorOutboxBlocked("mirror_stop_arguments_invalid")
        now = _utc(as_of or datetime.now(timezone.utc), "mirror_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            head = _head(self.db, event_sha256)
            _audit(self.db, event_sha256, head)
            if (not head or head["version"] != expected_outbox_version
                    or head["last_event_sha256"] != expected_head_sha256
                    or head["state"] not in ("QUEUED_BLOCKED", "CLAIMED_BLOCKED")
                    or (action == "UNCERTAIN"
                        and head["state"] != "CLAIMED_BLOCKED")):
                raise MirrorOutboxBlocked("mirror_stop_conflict")
            key = (head["account_id"], head["slot_id"], head["queue_id"])
            actor = _actor(self.db, verifier=verifier, bearer=bearer,
                           issuer=trusted_issuer, key=key, now=now)
            result = _write(
                self.db, event_sha256, old=head, action=action,
                operation_id=operation_id, key=key,
                writer_version=head["writer_version"],
                projection_sha256=head["projection_sha256"], actor=actor,
                reason="operator_cancelled" if action == "CANCEL"
                else "manual_unverified_outcome", now=now,
                lease_expires_at=head["lease_expires_at"],
            )
            self.db.commit()
            return result
        except MirrorOutboxBlocked:
            self.db.rollback()
            raise
        except sqlite3.IntegrityError:
            self.db.rollback()
            raise MirrorOutboxBlocked("mirror_duplicate_or_replay") from None
        except Exception:
            self.db.rollback()
            raise MirrorOutboxBlocked("mirror_stop_failed") from None

    def inspect(self, *, event_sha256: str) -> dict[str, Any]:
        _database(self.db)
        if not isinstance(event_sha256, str) or not SHA.fullmatch(event_sha256):
            raise MirrorOutboxBlocked("mirror_event_invalid")
        try:
            head = _head(self.db, event_sha256)
            _audit(self.db, event_sha256, head)
            if not head:
                return _result("NO_OUTBOX", 0, ZERO)
            result = _result(
                head["state"], head["version"], head["last_event_sha256"],
            )
            result["event_sha256"] = event_sha256
            result["claim_expires_at"] = head["lease_expires_at"]
            return result
        except sqlite3.Error:
            raise MirrorOutboxBlocked("mirror_inspection_failed") from None

    def pending_preview_ids(self, *, limit: int = 100) -> list[str]:
        """Only identities; never credentials, queue payloads or external I/O."""
        _database(self.db)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise MirrorOutboxBlocked("mirror_limit_invalid")
        result = []
        for (event_id,) in self.db.execute(
            """SELECT event_sha256 FROM sns_media_mirror_outbox_heads
               WHERE state='QUEUED_BLOCKED' ORDER BY updated_at LIMIT ?""",
            (limit,),
        ):
            head = _head(self.db, event_id)
            _audit(self.db, event_id, head)
            result.append(event_id)
        return result

    def acknowledge_external_delivery(self, **_unused: Any) -> None:
        """Not implemented: signed replica readback and service auth absent."""
        raise MirrorOutboxBlocked("mirror_delivery_ack_not_integrated")
