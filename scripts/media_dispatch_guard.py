#!/usr/bin/env python3
"""Phase 5B-6C: transactionally stage media dispatch *without* authorizing it.

5B-6A's media network interlock stays ON. This is a short-lived local
preparation barrier for a later single-store publisher service: there is no
operating system launcher, external queue writer, SNS credential or API call.
A Sheets snapshot cannot be locked by SQLite; no result is a live permit.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from media_publish_intent_authority import (
    _actor, _database, _head_row as _intent_head, _history as _intent_history,
    _preflight, _source,
)
from media_review_canonical_adapter import CanonicalProtectedReviewReader
from media_review_queue_reconciliation import _key
from media_review_trusted_precommit import _time, _utc
from media_review_verified_identity import PinnedRS256SessionVerifier

MIGRATION = (Path(__file__).resolve().parents[1] / "db" / "migrations"
             / "0005_sns_media_dispatch_guards.sql")
OP_ID = re.compile(r"dispatch_[A-Za-z0-9_.:-]{12,110}\Z")
ZERO = "0" * 64
SCHEMA = "sns_media_dispatch_event_v1"
STAGE_WINDOW = timedelta(seconds=60)
FIELDS = (
    "intent_version", "intent_event_sha256", "queue_sha256",
    "context_sha256", "content_sha256", "media_asset_id", "source_id",
    "staged_until",
)
HEAD_FIELDS = (
    "version", "state", *FIELDS, "last_event_sha256", "updated_at",
)
EVENT_FIELDS = frozenset((
    "schema_version", "operation_id", "action", "account_id", "slot_id",
    "queue_id", "version", "state", *FIELDS, "reason", "actor", "created_at",
    "previous_event_sha256",
))
TERMINALS = {
    "CANCEL": "CANCELLED_BLOCKED",
    "QUARANTINE": "DRIFT_BLOCKED",
    "MARK_UNCERTAIN": "OUTCOME_UNCERTAIN_BLOCKED",
}


class DispatchBlocked(ValueError):
    """A sanitized reason code only; never source text, token or raw URL."""


def initialize_dispatch_schema(db: sqlite3.Connection) -> None:
    """Explicit offline migration 0005; not a hidden mutation in request path."""
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise DispatchBlocked("dispatch_migration_requires_autocommit")
    try:
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='sns_media_publish_intent_heads'"
        ).fetchone() is None:
            raise DispatchBlocked("dispatch_intent_migration_required")
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
        db.execute("PRAGMA foreign_keys=ON")
    except (sqlite3.Error, OSError):
        raise DispatchBlocked("dispatch_migration_failed") from None


def _canon(value: dict[str, Any]) -> str:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=True, allow_nan=False,
        separators=(",", ":"),
    )


def _hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canon(value).encode("ascii")).hexdigest()


def _op(operation: str) -> None:
    if not isinstance(operation, str) or OP_ID.fullmatch(operation) is None:
        raise DispatchBlocked("dispatch_operation_invalid")


def _current(db: sqlite3.Connection, key: tuple[str, str, str]) -> dict[str, Any] | None:
    record = db.execute(
        "SELECT " + ",".join(HEAD_FIELDS) + """
         FROM sns_media_dispatch_heads
         WHERE account_id=? AND slot_id=? AND queue_id=?""", key,
    ).fetchone()
    return dict(zip(HEAD_FIELDS, record)) if record is not None else None


def _integrity(
    db: sqlite3.Connection, key: tuple[str, str, str],
    head: dict[str, Any] | None,
) -> None:
    rows = db.execute(
        """SELECT version,action,operation_id,previous_event_sha256,
                  event_sha256,payload_json
           FROM sns_media_dispatch_events
           WHERE account_id=? AND slot_id=? AND queue_id=? ORDER BY version""",
        key,
    ).fetchall()
    if head is None:
        if rows:
            raise DispatchBlocked("dispatch_orphan_events")
        return
    if (not rows or len(rows) != head["version"] or len(rows) > 64):
        raise DispatchBlocked("dispatch_history_count_invalid")
    prior = ZERO
    state = ""
    last: dict[str, Any] | None = None
    for number, (version, action, operation, previous, checksum, raw) in enumerate(rows, 1):
        try:
            event = json.loads(raw)
        except (TypeError, ValueError):
            raise DispatchBlocked("dispatch_history_corrupt") from None
        if (not isinstance(event, dict) or set(event) != EVENT_FIELDS
                or event["schema_version"] != SCHEMA
                or version != number or event["version"] != number
                or event["action"] != action or event["operation_id"] != operation
                or (event["account_id"], event["slot_id"], event["queue_id"]) != key
                or previous != prior or event["previous_event_sha256"] != prior
                or _hash(event) != checksum):
            raise DispatchBlocked("dispatch_history_tampered")
        expected = (
            "STAGED_BLOCKED" if number == 1 and action == "STAGE"
            else TERMINALS.get(action) if state == "STAGED_BLOCKED"
            else None
        )
        if expected is None or expected != event["state"]:
            raise DispatchBlocked("dispatch_lifecycle_tampered")
        if last is not None and any(event[f] != last[f] for f in FIELDS):
            raise DispatchBlocked("dispatch_snapshot_tampered")
        state, last, prior = expected, event, checksum
    assert last is not None
    for field in HEAD_FIELDS:
        expected = (prior if field == "last_event_sha256"
                    else last["created_at"] if field == "updated_at"
                    else last[field])
        if head[field] != expected:
            raise DispatchBlocked("dispatch_head_tampered")


def _result(state: str, version: int, digest: str) -> dict[str, Any]:
    return {
        "status": state, "dispatch_version": version,
        "last_event_sha256": digest,
        "effective_approval": False, "publish_authorized": False,
        "dispatch_allowed": False, "publish_attempted": False,
        "external_queue_atomicity_guaranteed": False,
        "ready_transitions_performed": False,
    }


def _insert(
    db: sqlite3.Connection, key: tuple[str, str, str], *,
    operation: str, action: str, actor: str, reason: str,
    old: dict[str, Any] | None, fields: dict[str, Any], now: datetime,
) -> dict[str, Any]:
    number = 1 if old is None else old["version"] + 1
    state = "STAGED_BLOCKED" if action == "STAGE" else TERMINALS[action]
    event = {
        "schema_version": SCHEMA, "operation_id": operation, "action": action,
        "account_id": key[0], "slot_id": key[1], "queue_id": key[2],
        "version": number, "state": state, **fields,
        "reason": reason, "actor": actor,
        "created_at": now.isoformat(timespec="seconds"),
        "previous_event_sha256": old["last_event_sha256"] if old else ZERO,
    }
    digest = _hash(event)
    if old is None:
        db.execute(
            """INSERT INTO sns_media_dispatch_heads(
               account_id,slot_id,queue_id,version,state,intent_version,
               intent_event_sha256,queue_sha256,context_sha256,content_sha256,
               media_asset_id,source_id,staged_until,last_event_sha256,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (*key, number, state, *(fields[f] for f in FIELDS),
             digest, event["created_at"]),
        )
    else:
        changed = db.execute(
            """UPDATE sns_media_dispatch_heads
               SET version=?,state=?,last_event_sha256=?,updated_at=?
               WHERE account_id=? AND slot_id=? AND queue_id=?
                 AND version=? AND last_event_sha256=?""",
            (number, state, digest, event["created_at"], *key,
             old["version"], old["last_event_sha256"]),
        )
        if changed.rowcount != 1:
            raise DispatchBlocked("dispatch_concurrent_change")
    db.execute(
        """INSERT INTO sns_media_dispatch_events (
           operation_id,account_id,slot_id,queue_id,version,action,
           previous_event_sha256,event_sha256,payload_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (operation, *key, number, action, event["previous_event_sha256"],
         digest, _canon(event)),
    )
    return _result(state, number, digest)


def _compare_intent(
    db: sqlite3.Connection, key: tuple[str, str, str],
    intent: dict[str, Any] | None, expected_intent_version: int,
    source: CanonicalProtectedReviewReader | None, now: datetime,
) -> datetime:
    if (not intent or intent["state"] != "HELD_BLOCKED"
            or type(expected_intent_version) is not int
            or intent["version"] != expected_intent_version):
        raise DispatchBlocked("dispatch_intent_unavailable")
    deadline = _time(intent["held_until"], "dispatch_intent_expired")
    if deadline <= now:
        raise DispatchBlocked("dispatch_intent_expired")
    ctx = _source(db, source, key)
    preflight = _preflight(
        db, key, ctx, intent["binding_version"],
        intent["review_version"], now,
    )
    for field in (
        "queue_sha256", "context_sha256", "content_sha256",
        "media_asset_id", "source_id", "review_version",
        "review_event_sha256", "binding_version", "binding_event_sha256",
    ):
        if preflight[field] != intent[field]:
            raise DispatchBlocked("dispatch_source_or_review_drift")
    return min(now + STAGE_WINDOW, deadline)


class MediaDispatchGuard:
    """Always deny live publish. Bound reviewer and intent share one SQLite DB."""

    def __init__(self, db: sqlite3.Connection) -> None:
        if not isinstance(db, sqlite3.Connection):
            raise DispatchBlocked("dispatch_database_unavailable")
        self.db = db

    def stage(
        self, *, key: tuple[str, str, str], operation_id: str,
        expected_intent_version: int,
        verifier: PinnedRS256SessionVerifier | None, bearer: str,
        trusted_issuer: str, source: CanonicalProtectedReviewReader | None,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        _database(self.db)
        key = _key(*key)
        _op(operation_id)
        now = _utc(as_of or datetime.now(timezone.utc), "dispatch_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            actor = _actor(
                self.db, verifier=verifier, bearer=bearer,
                issuer=trusted_issuer, key=key, now=now,
            )
            old = _current(self.db, key)
            _integrity(self.db, key, old)
            if old is not None:
                raise DispatchBlocked("dispatch_already_staged")
            intent = _intent_head(self.db, key)
            _intent_history(self.db, key, intent)
            until = _compare_intent(
                self.db, key, intent, expected_intent_version, source, now,
            )
            fields = {
                "intent_version": intent["version"],
                "intent_event_sha256": intent["last_event_sha256"],
                "queue_sha256": intent["queue_sha256"],
                "context_sha256": intent["context_sha256"],
                "content_sha256": intent["content_sha256"],
                "media_asset_id": intent["media_asset_id"],
                "source_id": intent["source_id"],
                "staged_until": until.isoformat(timespec="seconds"),
            }
            result = _insert(
                self.db, key, operation=operation_id, action="STAGE",
                actor=actor, reason="", old=None, fields=fields, now=now,
            )
            self.db.commit()
            return result
        except DispatchBlocked:
            self.db.rollback()
            raise
        except sqlite3.IntegrityError:
            self.db.rollback()
            raise DispatchBlocked("dispatch_duplicate_or_replay") from None
        except Exception:
            self.db.rollback()
            raise DispatchBlocked("dispatch_preparation_failed") from None

    def finalize_blocked(
        self, *, key: tuple[str, str, str], operation_id: str,
        expected_dispatch_version: int,
        action: str, verifier: PinnedRS256SessionVerifier | None,
        bearer: str, trusted_issuer: str,
        source: CanonicalProtectedReviewReader | None = None,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Finalize a staged local intent. No network delivery takes place.

        CANCEL and MARK_UNCERTAIN do not need an available external source.
        RECHECK can only return STAGED_BLOCKED or permanent DRIFT_BLOCKED.
        """
        _database(self.db)
        key = _key(*key)
        _op(operation_id)
        if (action not in ("CANCEL", "MARK_UNCERTAIN", "RECHECK")
                or type(expected_dispatch_version) is not int
                or expected_dispatch_version < 1):
            raise DispatchBlocked("dispatch_transition_invalid")
        now = _utc(as_of or datetime.now(timezone.utc), "dispatch_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            actor = _actor(
                self.db, verifier=verifier, bearer=bearer,
                issuer=trusted_issuer, key=key, now=now,
            )
            old = _current(self.db, key)
            _integrity(self.db, key, old)
            if not old or old["version"] != expected_dispatch_version:
                raise DispatchBlocked("dispatch_version_conflict")
            if old["state"] != "STAGED_BLOCKED":
                raise DispatchBlocked("dispatch_already_terminal")
            if self.db.execute(
                "SELECT 1 FROM sns_media_dispatch_events WHERE operation_id=?",
                (operation_id,),
            ).fetchone():
                raise DispatchBlocked("dispatch_operation_replayed")
            outcome_action = action
            reason = ("operator_cancelled" if action == "CANCEL"
                      else "unverified_external_outcome" if action == "MARK_UNCERTAIN"
                      else "source_or_rights_changed")
            if action == "RECHECK":
                try:
                    intent = _intent_head(self.db, key)
                    _intent_history(self.db, key, intent)
                    deadline = _compare_intent(
                        self.db, key, intent, old["intent_version"], source, now,
                    )
                    if (intent["last_event_sha256"] != old["intent_event_sha256"]
                            or any(intent[f] != old[f] for f in (
                                "queue_sha256", "context_sha256",
                                "content_sha256", "media_asset_id", "source_id",
                            ))
                            or _time(old["staged_until"], "dispatch_stage_expired") <= now):
                        raise DispatchBlocked("dispatch_source_or_stage_expired")
                    self.db.commit()
                    return _result("STAGED_BLOCKED", old["version"],
                                   old["last_event_sha256"])
                except Exception:
                    outcome_action = "QUARANTINE"
                    reason = "source_or_rights_changed"
            result = _insert(
                self.db, key, operation=operation_id,
                action=outcome_action, actor=actor, reason=reason,
                old=old, fields={f: old[f] for f in FIELDS}, now=now,
            )
            self.db.commit()
            return result
        except DispatchBlocked:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise DispatchBlocked("dispatch_transition_failed") from None

    def inspect(self, *, key: tuple[str, str, str]) -> dict[str, Any]:
        _database(self.db)
        key = _key(*key)
        try:
            head = _current(self.db, key)
            _integrity(self.db, key, head)
            return _result(
                head["state"] if head else "NO_DISPATCH",
                head["version"] if head else 0,
                head["last_event_sha256"] if head else ZERO,
            )
        except sqlite3.Error:
            raise DispatchBlocked("dispatch_inspection_failed") from None
