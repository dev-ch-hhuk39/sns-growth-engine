#!/usr/bin/env python3
"""Phase 5B-6F: authenticated, nonpublishing SQLite queue-command boundary.

Only safe queue management states and sanitized read-only mirror previews.
An actual Google Sheets writer, service identity, publisher and cutover are
absent. Never treat any result as a real-post permission.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from media_publish_intent_authority import _actor, _database
from media_review_canonical_adapter import CanonicalProtectedReviewReader
from media_review_protected_evidence import ProtectedEvidenceVault
from media_review_queue_reconciliation import _key, queue_fingerprint
from media_review_trusted_precommit import _utc
from media_review_verified_identity import PinnedRS256SessionVerifier
from media_shadow_queue_authority import (
    SQLiteShadowOperationalSnapshot, _history as _shadow_history,
    _may_refresh, _row as _shadow_row,
)

MIGRATION = (Path(__file__).resolve().parents[1] / "db" / "migrations"
             / "0007_sns_managed_queue_writer.sql")
OP_RE = re.compile(r"manage_[A-Za-z0-9_.:-]{12,110}\Z")
ZERO = "0" * 64
SCHEMA = "sns_managed_queue_event_v1"
MAX_EVENTS = 128
HEAD_FIELDS = (
    "version", "state", "shadow_version", "shadow_event_sha256",
    "queue_sha256", "last_event_sha256", "updated_at",
)
EVENT_FIELDS = frozenset((
    "schema_version", "operation_id", "account_id", "slot_id", "queue_id",
    "version", "state", "action", "shadow_version", "shadow_event_sha256",
    "queue_sha256", "actor", "reason", "created_at",
    "previous_event_sha256",
))
VALID_STATES = frozenset((
    "MANAGED_BLOCKED", "HOLD_BLOCKED",
    "ARCHIVED_BLOCKED", "CONFLICT_BLOCKED",
))


class ManagedQueueBlocked(ValueError):
    """Public-safe reason codes only, never source/identity provider bodies."""


def initialize_managed_queue_schema(db: sqlite3.Connection) -> None:
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise ManagedQueueBlocked("managed_migration_requires_autocommit")
    try:
        needed = ("sns_media_shadow_queue_heads", "sns_media_review_heads",
                  "sns_review_sessions", "sns_media_dispatch_heads")
        for table in needed:
            if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone():
                raise ManagedQueueBlocked("managed_migration_missing_parent")
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
        db.execute("PRAGMA foreign_keys=ON")
    except (sqlite3.Error, OSError):
        raise ManagedQueueBlocked("managed_migration_failed") from None


def _canon(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    )


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canon(payload).encode("ascii")).hexdigest()


def _row(db: sqlite3.Connection, key: tuple[str, str, str]) -> dict[str, Any] | None:
    found = db.execute(
        "SELECT " + ",".join(HEAD_FIELDS) + """
         FROM sns_media_managed_queue_heads
         WHERE account_id=? AND slot_id=? AND queue_id=?""", key,
    ).fetchone()
    return dict(zip(HEAD_FIELDS, found)) if found is not None else None


def _history(db: sqlite3.Connection, key: tuple[str, str, str],
             head: dict[str, Any] | None) -> None:
    records = db.execute(
        """SELECT version,action,operation_id,previous_event_sha256,
                  event_sha256,payload_json
           FROM sns_media_managed_queue_events
           WHERE account_id=? AND slot_id=? AND queue_id=? ORDER BY version""",
        key,
    ).fetchall()
    if head is None:
        if records:
            raise ManagedQueueBlocked("managed_history_orphan")
        return
    if (head["state"] not in VALID_STATES or not records
            or len(records) != head["version"] or len(records) > MAX_EVENTS):
        raise ManagedQueueBlocked("managed_history_invalid")
    prev = ZERO
    state = ""
    last: dict[str, Any] | None = None
    for number, (version, action, op, before, digest, raw) in enumerate(records, 1):
        try:
            event = json.loads(raw)
        except (ValueError, TypeError):
            raise ManagedQueueBlocked("managed_history_corrupt") from None
        if (not isinstance(event, dict) or set(event) != EVENT_FIELDS
                or event["schema_version"] != SCHEMA
                or event["operation_id"] != op or event["version"] != number
                or version != number or event["action"] != action
                or tuple(event[name] for name in (
                    "account_id", "slot_id", "queue_id",
                )) != key
                or before != prev or event["previous_event_sha256"] != before
                or _hash(event) != digest):
            raise ManagedQueueBlocked("managed_history_tampered")
        expected = (
            "MANAGED_BLOCKED" if number == 1 and action == "BIND"
            else "MANAGED_BLOCKED" if (
                action == "RECONCILE" and state == "MANAGED_BLOCKED"
            )
            else "HOLD_BLOCKED" if action == "HOLD" and state == "MANAGED_BLOCKED"
            else "ARCHIVED_BLOCKED" if action == "ARCHIVE"
            and state in ("MANAGED_BLOCKED", "HOLD_BLOCKED")
            else "CONFLICT_BLOCKED" if action == "QUARANTINE"
            and state in ("MANAGED_BLOCKED", "HOLD_BLOCKED")
            else None
        )
        if expected is None or event["state"] != expected:
            raise ManagedQueueBlocked("managed_history_transition_invalid")
        if last and (
            event["queue_sha256"] != last["queue_sha256"]
            or (
                action != "RECONCILE"
                and (event["shadow_version"], event["shadow_event_sha256"]) != (
                    last["shadow_version"], last["shadow_event_sha256"]
                )
            )
            or (
                action == "RECONCILE"
                and event["shadow_version"] <= last["shadow_version"]
            )
        ):
            raise ManagedQueueBlocked("managed_history_identity_changed")
        state, last, prev = expected, event, digest
    assert last is not None
    for field in HEAD_FIELDS:
        actual = (prev if field == "last_event_sha256"
                  else last["created_at"] if field == "updated_at"
                  else last[field])
        if head[field] != actual:
            raise ManagedQueueBlocked("managed_head_tampered")


def _expected(head: dict[str, Any] | None, version: int, sha: str) -> None:
    if type(version) is not int or not isinstance(sha, str):
        raise ManagedQueueBlocked("managed_expected_invalid")
    if head is None:
        if version != 0 or sha != ZERO:
            raise ManagedQueueBlocked("managed_version_conflict")
    elif head["version"] != version or head["last_event_sha256"] != sha:
        raise ManagedQueueBlocked("managed_version_conflict")


def _projection(key: tuple[str, str, str], *, version: int,
                state: str, digest: str, shadow_sha: str,
                queue_sha: str) -> dict[str, Any]:
    """Sanitized read-only reference: NEVER a publishable queue row."""
    return {
        "schema": "sns_sheet_read_only_mirror_preview_v1",
        "account_id": key[0], "slot_id": key[1], "queue_id": key[2],
        "writer_version": version, "writer_event_sha256": digest,
        "shadow_event_sha256": shadow_sha, "queue_sha256": queue_sha,
        "writer_state": state, "view_only": True,
        "ready_transitions_performed": False, "publish_authorized": False,
    }


def _append(db: sqlite3.Connection, key: tuple[str, str, str], *,
            old: dict[str, Any] | None, action: str, operation_id: str,
            actor: str, now: datetime, reason: str,
            shadow_version: int, shadow_sha: str,
            queue_sha: str) -> dict[str, Any]:
    version = 1 if old is None else old["version"] + 1
    if version > MAX_EVENTS:
        raise ManagedQueueBlocked("managed_history_capacity")
    state = {
        "BIND": "MANAGED_BLOCKED", "RECONCILE": "MANAGED_BLOCKED",
        "HOLD": "HOLD_BLOCKED",
        "ARCHIVE": "ARCHIVED_BLOCKED", "QUARANTINE": "CONFLICT_BLOCKED",
    }[action]
    event = {
        "schema_version": SCHEMA, "operation_id": operation_id,
        "account_id": key[0], "slot_id": key[1], "queue_id": key[2],
        "version": version, "state": state, "action": action,
        "shadow_version": shadow_version,
        "shadow_event_sha256": shadow_sha, "queue_sha256": queue_sha,
        "actor": actor, "reason": reason,
        "created_at": now.isoformat(timespec="seconds"),
        "previous_event_sha256": old["last_event_sha256"] if old else ZERO,
    }
    digest = _hash(event)
    if old is None:
        db.execute(
            """INSERT INTO sns_media_managed_queue_heads(
               account_id,slot_id,queue_id,version,state,shadow_version,
               shadow_event_sha256,queue_sha256,last_event_sha256,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (*key, version, state, shadow_version,
             shadow_sha, queue_sha, digest, event["created_at"]),
        )
    else:
        changed = db.execute(
            """UPDATE sns_media_managed_queue_heads
               SET version=?,state=?,shadow_version=?,shadow_event_sha256=?,
                   queue_sha256=?,last_event_sha256=?,updated_at=?
               WHERE account_id=? AND slot_id=? AND queue_id=?
                AND version=? AND last_event_sha256=?""",
            (version, state, shadow_version, shadow_sha, queue_sha,
             digest, event["created_at"], *key,
             old["version"], old["last_event_sha256"]),
        )
        if changed.rowcount != 1:
            raise ManagedQueueBlocked("managed_concurrent_change")
    db.execute(
        """INSERT INTO sns_media_managed_queue_events(
           operation_id,account_id,slot_id,queue_id,version,action,
           previous_event_sha256,event_sha256,payload_json)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (operation_id, *key, version, action,
         event["previous_event_sha256"], digest, _canon(event)),
    )
    projection = _projection(
        key, version=version, state=state, digest=digest,
        shadow_sha=shadow_sha, queue_sha=queue_sha,
    )
    db.execute(
        """INSERT INTO sns_media_sheet_mirror_previews(
           event_sha256,account_id,slot_id,queue_id,
           writer_version,projection_sha256,projection_json)
           VALUES(?,?,?,?,?,?,?)""",
        (digest, *key, version, _hash(projection), _canon(projection)),
    )
    # Migration 0008's outbox (if provisioned) must be created inside this
    # SAME transaction. Otherwise a crash after commit could silently leave
    # an untracked mirror event. Older schemas remain backwards-compatible.
    from media_mirror_outbox import enqueue_in_managed_write
    enqueue_in_managed_write(
        db, event_id=digest, key=key,
        writer_version=version, projection_sha256=_hash(projection), now=now,
    )
    return {
        "status": state, "writer_version": version,
        "writer_event_sha256": digest,
        "effective_approval": False, "publish_authorized": False,
        "dispatch_allowed": False, "sheets_write_allowed": False,
        "mirror_published": False, "ready_transitions_performed": False,
        "external_queue_atomicity_guaranteed": False,
    }


def _check_shadow(db: sqlite3.Connection, key: tuple[str, str, str],
                  head: dict[str, Any]) -> None:
    shadow = _shadow_row(db, key)
    _shadow_history(db, key, shadow)
    if (not shadow or shadow["state"] != "SHADOW_BLOCKED"
            or shadow["version"] != head["shadow_version"]
            or shadow["last_event_sha256"] != head["shadow_event_sha256"]
            or shadow["queue_sha256"] != head["queue_sha256"]):
        raise ManagedQueueBlocked("managed_shadow_drift")


def check_managed_queue_read(
    db: sqlite3.Connection, key: tuple[str, str, str],
) -> None:
    """Mandatory before reading the managed (opt-in) operational adapter."""
    head = _row(db, key)
    _history(db, key, head)
    if not head or head["state"] != "MANAGED_BLOCKED":
        raise ManagedQueueBlocked("managed_read_blocked")
    _check_shadow(db, key, head)


class SQLiteManagedOperationalSnapshot:
    """Opt-in reader for downstream review/intent/dispatch; same SQLite DB."""

    def __init__(
        self, *, db: sqlite3.Connection, vault: ProtectedEvidenceVault,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.db = db
        self.source = SQLiteShadowOperationalSnapshot(
            db=db, vault=vault, clock=clock,
        )

    def load(self, account_id: str, slot_id: str, queue_id: str):
        key = _key(account_id, slot_id, queue_id)
        try:
            check_managed_queue_read(self.db, key)
            return self.source.load(*key)
        except Exception:
            raise ManagedQueueBlocked("managed_source_unavailable") from None


class MediaManagedQueueWriter:
    """Authenticated queue control, only BLOCKED states; no Sheets transport."""

    def __init__(self, db: sqlite3.Connection):
        if not isinstance(db, sqlite3.Connection):
            raise ManagedQueueBlocked("managed_database_invalid")
        self.db = db

    def bind(
        self, *, key: tuple[str, str, str], operation_id: str,
        verifier: PinnedRS256SessionVerifier | None,
        bearer: str, trusted_issuer: str,
        canonical: CanonicalProtectedReviewReader | None,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Bind a validated shadow before any review; no queue body mutation."""
        _database(self.db)
        key = _key(*key)
        if not isinstance(operation_id, str) or not OP_RE.fullmatch(operation_id):
            raise ManagedQueueBlocked("managed_operation_invalid")
        now = _utc(as_of or datetime.now(timezone.utc), "managed_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            actor = _actor(self.db, verifier=verifier, bearer=bearer,
                           issuer=trusted_issuer, key=key, now=now)
            old = _row(self.db, key)
            _history(self.db, key, old)
            if old or not _may_refresh(self.db, key):
                raise ManagedQueueBlocked("managed_existing_or_review_frozen")
            if (not isinstance(canonical, CanonicalProtectedReviewReader)
                    or canonical.vault.connection is not self.db
                    or not isinstance(canonical.source, SQLiteShadowOperationalSnapshot)
                    or canonical.source.db is not self.db):
                raise ManagedQueueBlocked("managed_bootstrap_source_invalid")
            context = canonical.load_current(*key)
            shadow = _shadow_row(self.db, key)
            _shadow_history(self.db, key, shadow)
            if (not shadow or shadow["state"] != "SHADOW_BLOCKED"
                    or shadow["queue_sha256"] != queue_fingerprint(context.queue)):
                raise ManagedQueueBlocked("managed_shadow_unavailable")
            result = _append(
                self.db, key, old=None, action="BIND",
                operation_id=operation_id, actor=actor, reason="",
                now=now, shadow_version=shadow["version"],
                shadow_sha=shadow["last_event_sha256"],
                queue_sha=shadow["queue_sha256"],
            )
            self.db.commit()
            return result
        except ManagedQueueBlocked:
            self.db.rollback()
            raise
        except sqlite3.IntegrityError:
            self.db.rollback()
            raise ManagedQueueBlocked("managed_duplicate_or_replay") from None
        except Exception:
            self.db.rollback()
            raise ManagedQueueBlocked("managed_bind_denied") from None

    def reconcile_observation(
        self, *, key: tuple[str, str, str], operation_id: str,
        expected_version: int, expected_head_sha256: str,
        verifier: PinnedRS256SessionVerifier | None,
        bearer: str, trusted_issuer: str,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Accept only newer, same-content shadow OBSERVE events; never REFRESH.

        A fresh observation is recorded in a separate transaction, so the
        managed adapter fails closed until this CAS reconciliation succeeds.
        No queue content, rights, review, READY or external Sheet is changed.
        """
        _database(self.db)
        key = _key(*key)
        if not isinstance(operation_id, str) or not OP_RE.fullmatch(operation_id):
            raise ManagedQueueBlocked("managed_operation_invalid")
        now = _utc(as_of or datetime.now(timezone.utc), "managed_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            actor = _actor(self.db, verifier=verifier, bearer=bearer,
                           issuer=trusted_issuer, key=key, now=now)
            head = _row(self.db, key)
            _history(self.db, key, head)
            _expected(head, expected_version, expected_head_sha256)
            if not head or head["state"] != "MANAGED_BLOCKED":
                raise ManagedQueueBlocked("managed_reconcile_state_invalid")
            shadow = _shadow_row(self.db, key)
            _shadow_history(self.db, key, shadow)
            if (not shadow or shadow["state"] != "SHADOW_BLOCKED"
                    or shadow["queue_sha256"] != head["queue_sha256"]
                    or shadow["version"] <= head["shadow_version"]):
                raise ManagedQueueBlocked("managed_reconcile_drift")
            # Cross-check every intermediate observation, not just the head.
            newer = self.db.execute(
                """SELECT action,payload_json
                   FROM sns_media_shadow_queue_events
                   WHERE account_id=? AND slot_id=? AND queue_id=?
                     AND version>? ORDER BY version""",
                (*key, head["shadow_version"]),
            ).fetchall()
            if len(newer) != shadow["version"] - head["shadow_version"]:
                raise ManagedQueueBlocked("managed_reconcile_history_gap")
            for action, raw in newer:
                event = json.loads(raw)
                if (action != "OBSERVE"
                        or event["queue_sha256"] != head["queue_sha256"]
                        or event["context_sha256"] != shadow["context_sha256"]
                        or event["snapshot_sha256"] != shadow["snapshot_sha256"]):
                    raise ManagedQueueBlocked("managed_reconcile_drift")
            result = _append(
                self.db, key, old=head, action="RECONCILE",
                operation_id=operation_id, actor=actor,
                reason="same_content_observation", now=now,
                shadow_version=shadow["version"],
                shadow_sha=shadow["last_event_sha256"],
                queue_sha=shadow["queue_sha256"],
            )
            self.db.commit()
            return result
        except ManagedQueueBlocked:
            self.db.rollback()
            raise
        except sqlite3.IntegrityError:
            self.db.rollback()
            raise ManagedQueueBlocked("managed_duplicate_or_replay") from None
        except Exception:
            self.db.rollback()
            raise ManagedQueueBlocked("managed_reconcile_failed") from None

    def transition(
        self, *, key: tuple[str, str, str], operation_id: str,
        action: str, expected_version: int, expected_head_sha256: str,
        verifier: PinnedRS256SessionVerifier | None,
        bearer: str, trusted_issuer: str,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Only protective HOLD, ARCHIVE, QUARANTINE transitions."""
        _database(self.db)
        key = _key(*key)
        if (not isinstance(operation_id, str) or not OP_RE.fullmatch(operation_id)
                or action not in ("HOLD", "ARCHIVE", "QUARANTINE")):
            raise ManagedQueueBlocked("managed_transition_invalid")
        now = _utc(as_of or datetime.now(timezone.utc), "managed_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            actor = _actor(self.db, verifier=verifier, bearer=bearer,
                           issuer=trusted_issuer, key=key, now=now)
            head = _row(self.db, key)
            _history(self.db, key, head)
            _expected(head, expected_version, expected_head_sha256)
            if head is None or head["state"] not in (
                "MANAGED_BLOCKED", "HOLD_BLOCKED",
            ) or (action == "HOLD" and head["state"] != "MANAGED_BLOCKED"):
                raise ManagedQueueBlocked("managed_terminal_or_missing")
            # All actions only reduce permission. A drift is also terminal.
            result = _append(
                self.db, key, old=head, action=action,
                operation_id=operation_id, actor=actor,
                reason="operator_safety_control", now=now,
                shadow_version=head["shadow_version"],
                shadow_sha=head["shadow_event_sha256"],
                queue_sha=head["queue_sha256"],
            )
            self.db.commit()
            return result
        except ManagedQueueBlocked:
            self.db.rollback()
            raise
        except sqlite3.IntegrityError:
            self.db.rollback()
            raise ManagedQueueBlocked("managed_operation_replayed") from None
        except Exception:
            self.db.rollback()
            raise ManagedQueueBlocked("managed_transition_failed") from None

    def inspect(self, *, key: tuple[str, str, str]) -> dict[str, Any]:
        _database(self.db)
        key = _key(*key)
        try:
            head = _row(self.db, key)
            _history(self.db, key, head)
            return {
                "status": head["state"] if head else "NO_MANAGED_QUEUE",
                "writer_version": head["version"] if head else 0,
                "writer_event_sha256": head["last_event_sha256"] if head else ZERO,
                "publish_authorized": False, "sheets_write_allowed": False,
            }
        except sqlite3.Error:
            raise ManagedQueueBlocked("managed_inspection_failed") from None

    def mirror_previews(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """Read-only plan, ONLY newest event per queue; no Sheets transport."""
        _database(self.db)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ManagedQueueBlocked("managed_mirror_limit_invalid")
        records = self.db.execute(
            """SELECT m.account_id,m.slot_id,m.queue_id,m.writer_version,
                      m.event_sha256,m.projection_sha256,m.projection_json
               FROM sns_media_sheet_mirror_previews m
               JOIN sns_media_managed_queue_heads h ON
                 m.account_id=h.account_id AND m.slot_id=h.slot_id
                 AND m.queue_id=h.queue_id AND m.writer_version=h.version
               ORDER BY m.account_id,m.slot_id,m.queue_id LIMIT ?""",
            (limit,),
        ).fetchall()
        previews = []
        for account, slot, queue, version, digest, checksum, raw in records:
            key = _key(account, slot, queue)
            head = _row(self.db, key)
            _history(self.db, key, head)
            if not head or head["last_event_sha256"] != digest or head["version"] != version:
                raise ManagedQueueBlocked("managed_mirror_out_of_sync")
            try:
                projection = json.loads(raw)
            except (TypeError, ValueError):
                raise ManagedQueueBlocked("managed_mirror_corrupt") from None
            if (not isinstance(projection, dict) or _hash(projection) != checksum
                    or projection != _projection(
                        key, version=version, state=head["state"],
                        digest=digest,
                        shadow_sha=head["shadow_event_sha256"],
                        queue_sha=head["queue_sha256"],
                    )):
                raise ManagedQueueBlocked("managed_mirror_tampered")
            previews.append(projection)
        return previews
