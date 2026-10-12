#!/usr/bin/env python3
"""Phase 5B-6B: non-authorizing, atomic SQLite media publication intent journal.

A HOLD means that *one* current source snapshot was checked and recorded. It
does not grant publication: the external Sheets queue can still drift, the
publisher cannot atomically claim a remote API outcome, and there is no live
publish authority. Neither returned data nor this database contains a
publishable permit. Phase 5B-6A's real-media network interlock stays absolute.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from media_review_canonical_adapter import CanonicalProtectedReviewReader
from media_review_queue_reconciliation import (
    _current_review_still_valid, _key, _row, _verify_history,
    context_fingerprint, queue_fingerprint,
)
from media_review_transactional_ledger import (
    _head, _validate_event_history,
)
from media_review_trusted_precommit import (
    CanonicalReviewContext, ReviewRequest, _check_principal, _time, _utc,
)
from media_review_verified_identity import PinnedRS256SessionVerifier

MIGRATION = (Path(__file__).resolve().parents[1] / "db" / "migrations"
             / "0004_sns_media_publish_intents.sql")
OP_ID = re.compile(r"intent_[A-Za-z0-9_.:-]{12,110}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")
ZERO = "0" * 64
MAX_HISTORY = 128
MAX_CAPTION_BYTES = 16_000
MAX_HOLD = timedelta(minutes=5)
SCHEMA = "sns_media_publish_intent_event_v1"
EVENT_FIELDS = frozenset({
    "schema_version", "operation_id", "action", "account_id", "slot_id",
    "queue_id", "version", "state", "queue_sha256", "context_sha256",
    "content_sha256", "media_asset_id", "source_id", "review_version",
    "review_event_sha256", "binding_version", "binding_event_sha256",
    "held_until", "actor", "reason", "created_at", "previous_event_sha256",
})
HEAD_FIELDS = (
    "version", "state", "queue_sha256", "context_sha256", "content_sha256",
    "media_asset_id", "source_id", "review_version",
    "review_event_sha256", "binding_version", "binding_event_sha256",
    "held_until", "last_event_sha256", "updated_at",
)
SAFE_REASON_CODES = frozenset({
    "operator_cancelled", "source_unavailable", "queue_drift",
    "rights_or_review_invalid", "reservation_expired",
})


class PublishIntentBlocked(ValueError):
    """Only stable error codes; never a source URL, token or caption."""


def initialize_intent_schema(db: sqlite3.Connection) -> None:
    """Explicit trusted-operator migration; never auto-create during a call."""
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise PublishIntentBlocked("intent_migration_requires_autocommit")
    try:
        for table in (
            "sns_media_review_heads", "sns_media_review_queue_bindings",
            "sns_review_sessions", "sns_review_evidence_events",
        ):
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,),
            ).fetchone() is None:
                raise PublishIntentBlocked("intent_prerequisite_migration_missing")
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
        db.execute("PRAGMA foreign_keys=ON")
    except (sqlite3.Error, OSError):
        raise PublishIntentBlocked("intent_migration_failed") from None


def _database(db: sqlite3.Connection) -> None:
    try:
        if (not isinstance(db, sqlite3.Connection) or db.in_transaction
                or db.execute("PRAGMA foreign_keys").fetchone()[0] != 1):
            raise PublishIntentBlocked("intent_database_unavailable")
    except sqlite3.Error:
        raise PublishIntentBlocked("intent_database_unavailable") from None


def _canon(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    )


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canon(payload).encode("ascii")).hexdigest()


def _head_row(db: sqlite3.Connection, key: tuple[str, str, str]) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT " + ",".join(HEAD_FIELDS) + """
          FROM sns_media_publish_intent_heads
          WHERE account_id=? AND slot_id=? AND queue_id=?""", key,
    ).fetchone()
    return dict(zip(HEAD_FIELDS, row)) if row is not None else None


def _history(db: sqlite3.Connection, key: tuple[str, str, str],
             head: dict[str, Any] | None) -> None:
    rows = db.execute(
        """SELECT version,action,operation_id,previous_event_sha256,
                  event_sha256,payload_json
           FROM sns_media_publish_intent_events
           WHERE account_id=? AND slot_id=? AND queue_id=?
           ORDER BY version""", key,
    ).fetchall()
    if head is None:
        if rows:
            raise PublishIntentBlocked("intent_orphan_history")
        return
    if (not rows or len(rows) != head["version"]
            or len(rows) > MAX_HISTORY):
        raise PublishIntentBlocked("intent_history_invalid")
    previous = ZERO
    state = ""
    last: dict[str, Any] = {}
    for index, (version, action, operation, prev, digest, raw) in enumerate(rows, 1):
        try:
            event = json.loads(raw)
        except (TypeError, ValueError):
            raise PublishIntentBlocked("intent_history_corrupt") from None
        if (not isinstance(event, dict) or set(event) != EVENT_FIELDS
                or event.get("schema_version") != SCHEMA
                or version != index or event["version"] != index
                or event["action"] != action or event["operation_id"] != operation
                or (event["account_id"], event["slot_id"], event["queue_id"]) != key
                or prev != previous or event["previous_event_sha256"] != prev
                or digest != _digest(event)):
            raise PublishIntentBlocked("intent_history_tampered")
        expected = (
            "HELD_BLOCKED" if action == "HOLD" and not state and index == 1
            else "CANCELLED_BLOCKED" if action == "CANCEL" and state == "HELD_BLOCKED"
            else "QUARANTINED_BLOCKED" if action == "QUARANTINE" and state == "HELD_BLOCKED"
            else ""
        )
        if not expected or event["state"] != expected:
            raise PublishIntentBlocked("intent_history_transition_invalid")
        if index > 1 and any(
            event[field] != last[field] for field in (
                "queue_sha256", "context_sha256", "content_sha256",
                "media_asset_id", "source_id", "review_version",
                "review_event_sha256", "binding_version",
                "binding_event_sha256", "held_until",
            )
        ):
            raise PublishIntentBlocked("intent_history_target_changed")
        state, previous, last = expected, digest, event
    for key_name in HEAD_FIELDS:
        expected = (previous if key_name == "last_event_sha256"
                    else last["created_at"] if key_name == "updated_at"
                    else last[key_name])
        if head[key_name] != expected:
            raise PublishIntentBlocked("intent_head_tampered")


def _actor(
    db: sqlite3.Connection, *, verifier: PinnedRS256SessionVerifier | None,
    bearer: str, issuer: str, key: tuple[str, str, str], now: datetime,
) -> str:
    if (not isinstance(verifier, PinnedRS256SessionVerifier)
            or verifier._sessions.connection is not db
            or not isinstance(bearer, str) or not bearer.startswith("Bearer ")
            or len(bearer.split()) != 2 or not issuer):
        raise PublishIntentBlocked("intent_operator_unavailable")
    request = ReviewRequest(
        account_id=key[0], slot_id=key[1], queue_id=key[2],
        expected_queue_revision="revision00000001",
        expected_plan_sha256=ZERO, expected_receipts_head_sha256=ZERO,
        draft_event_sha256=ZERO, confirm_human_review=True,
    )
    try:
        principal = verifier.verify(bearer[7:], now=now)
        principal = _check_principal(principal, request, now, issuer)
        return principal.subject
    except Exception:
        raise PublishIntentBlocked("intent_operator_unauthorized") from None


def _source(
    db: sqlite3.Connection, source: CanonicalProtectedReviewReader | None,
    key: tuple[str, str, str],
) -> CanonicalReviewContext:
    if (not isinstance(source, CanonicalProtectedReviewReader)
            or source.vault.connection is not db):
        raise PublishIntentBlocked("intent_trusted_source_unavailable")
    try:
        result = source.load_current(*key)
        if not isinstance(result, CanonicalReviewContext):
            raise ValueError()
        return result
    except Exception:
        raise PublishIntentBlocked("intent_trusted_source_unavailable") from None


def _preflight(
    db: sqlite3.Connection, key: tuple[str, str, str],
    context: CanonicalReviewContext, expected_binding_version: int,
    expected_review_version: int, now: datetime,
) -> dict[str, Any]:
    bound = _row(db, key)
    _verify_history(db, key, bound)
    head = _head(db, key)
    _validate_event_history(db, key, head)
    if (bound is None or head["state"] != "REVIEW_RECORDED_ONLY"
            or bound["state"] != "REVIEW_RECORDED_BLOCKED"
            or bound["reconciliation_state"] != "MATCHED_BLOCKED"
            or type(expected_binding_version) is not int
            or type(expected_review_version) is not int
            or bound["binding_version"] != expected_binding_version
            or head["version"] != expected_review_version
            or bound["ledger_version"] != head["version"]
            or bound["ledger_event_sha256"] != head["hash"]):
        raise PublishIntentBlocked("intent_review_or_binding_not_current")
    if (queue_fingerprint(context.queue) != bound["queue_sha256"]
            or context_fingerprint(context) != bound["context_sha256"]
            or not _current_review_still_valid(db, key, bound, context, now)):
        raise PublishIntentBlocked("intent_rights_or_queue_not_current")
    # The recorded human reviewer must still have an enabled grant and no
    # explicitly revoked source session. Natural JWT expiry is not a retroactive
    # withdrawal; explicit session or grant revocation is.
    review_event = db.execute(
        """SELECT payload_json FROM sns_media_review_events
           WHERE account_id=? AND slot_id=? AND queue_id=? AND sequence=?""",
        (*key, head["version"]),
    ).fetchone()
    if review_event is None:
        raise PublishIntentBlocked("intent_review_missing")
    payload = json.loads(review_event[0])
    subject = payload["reviewer_subject"]
    grant = db.execute(
        """SELECT 1 FROM sns_review_account_grants WHERE subject=?
           AND account_id=? AND enabled=1
           AND role IN ('MEDIA_REVIEWER','ADMIN') LIMIT 1""",
        (subject, key[0]),
    ).fetchone()
    sessions = db.execute(
        """SELECT COUNT(*),SUM(CASE WHEN revoked_at IS NOT NULL THEN 1 ELSE 0 END)
           FROM sns_review_sessions WHERE subject=?""", (subject,),
    ).fetchone()
    if not grant or not sessions or sessions[0] < 1 or sessions[1]:
        raise PublishIntentBlocked("intent_reviewer_revoked")
    queue = context.queue
    caption = queue.get("public_post_text")
    media_id = queue.get("media_asset_id")
    source_id = queue.get("source_id")
    if (not isinstance(caption, str) or not caption.strip()
            or len(caption.encode("utf-8")) > MAX_CAPTION_BYTES
            or not isinstance(media_id, str) or not media_id
            or not isinstance(source_id, str) or not source_id):
        raise PublishIntentBlocked("intent_content_or_asset_invalid")
    rights_end = _time(payload["rights_expire_at"], "intent_rights_expired")
    if rights_end <= now:
        raise PublishIntentBlocked("intent_rights_expired")
    held_until = min(now + MAX_HOLD, rights_end)
    return {
        "queue_sha256": bound["queue_sha256"],
        "context_sha256": bound["context_sha256"],
        "content_sha256": hashlib.sha256(caption.encode("utf-8")).hexdigest(),
        "media_asset_id": media_id, "source_id": source_id,
        "review_version": head["version"], "review_event_sha256": head["hash"],
        "binding_version": bound["binding_version"],
        "binding_event_sha256": bound["last_event_sha256"],
        "held_until": held_until.isoformat(timespec="seconds"),
    }


def _append(
    db: sqlite3.Connection, key: tuple[str, str, str], *,
    old: dict[str, Any] | None,
    action: str, operation_id: str, actor: str, reason: str,
    now: datetime, fields: dict[str, Any],
) -> dict[str, Any]:
    version = 1 if old is None else old["version"] + 1
    if version > MAX_HISTORY:
        raise PublishIntentBlocked("intent_history_at_capacity")
    state = {
        "HOLD": "HELD_BLOCKED", "CANCEL": "CANCELLED_BLOCKED",
        "QUARANTINE": "QUARANTINED_BLOCKED",
    }[action]
    payload = {
        "schema_version": SCHEMA, "operation_id": operation_id,
        "action": action, "account_id": key[0], "slot_id": key[1],
        "queue_id": key[2], "version": version, "state": state,
        **fields, "actor": actor, "reason": reason,
        "created_at": now.isoformat(timespec="seconds"),
        "previous_event_sha256": old["last_event_sha256"] if old else ZERO,
    }
    digest = _digest(payload)
    if old is None:
        db.execute(
            """INSERT INTO sns_media_publish_intent_heads
               (account_id,slot_id,queue_id,version,state,queue_sha256,
                context_sha256,content_sha256,media_asset_id,source_id,
                review_version,review_event_sha256,binding_version,
                binding_event_sha256,held_until,last_event_sha256,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (*key, version, state, *(fields[name] for name in (
                "queue_sha256", "context_sha256", "content_sha256",
                "media_asset_id", "source_id", "review_version",
                "review_event_sha256", "binding_version",
                "binding_event_sha256", "held_until",
            )), digest, payload["created_at"]),
        )
    else:
        updated = db.execute(
            """UPDATE sns_media_publish_intent_heads
               SET version=?,state=?,last_event_sha256=?,updated_at=?
               WHERE account_id=? AND slot_id=? AND queue_id=?
                  AND version=? AND last_event_sha256=?""",
            (version, state, digest, payload["created_at"], *key,
             old["version"], old["last_event_sha256"]),
        )
        if updated.rowcount != 1:
            raise PublishIntentBlocked("intent_concurrent_change")
    db.execute(
        """INSERT INTO sns_media_publish_intent_events
           (operation_id,account_id,slot_id,queue_id,version,action,
            previous_event_sha256,event_sha256,payload_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (operation_id, *key, version, action,
         payload["previous_event_sha256"], digest, _canon(payload)),
    )
    return {
        "status": state, "event_sha256": digest, "intent_version": version,
        "effective_approval": False, "publish_authorized": False,
        "ready_transitions_performed": False, "external_queue_atomicity_guaranteed": False,
        "publish_attempted": False,
    }


class MediaPublishIntents:
    """Trusted injection-only service over the SAME SQLite review database."""

    def __init__(self, db: sqlite3.Connection) -> None:
        if not isinstance(db, sqlite3.Connection):
            raise PublishIntentBlocked("intent_database_unavailable")
        self.db = db

    def reserve(
        self, *, key: tuple[str, str, str], operation_id: str,
        expected_binding_version: int, expected_review_version: int,
        verifier: PinnedRS256SessionVerifier | None,
        bearer: str, trusted_issuer: str,
        source: CanonicalProtectedReviewReader | None,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Record a time-bounded HOLD_BLOCKED, NEVER create a usable permit."""
        _database(self.db)
        key = _key(*key)
        if not isinstance(operation_id, str) or OP_ID.fullmatch(operation_id) is None:
            raise PublishIntentBlocked("intent_operation_invalid")
        now = _utc(as_of or datetime.now(timezone.utc), "intent_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            actor = _actor(
                self.db, verifier=verifier, bearer=bearer,
                issuer=trusted_issuer, key=key, now=now,
            )
            old = _head_row(self.db, key)
            _history(self.db, key, old)
            if old is not None:
                raise PublishIntentBlocked("intent_already_consumed")
            context = _source(self.db, source, key)
            fields = _preflight(
                self.db, key, context, expected_binding_version,
                expected_review_version, now,
            )
            result = _append(
                self.db, key, old=None, action="HOLD",
                operation_id=operation_id, actor=actor, reason="",
                now=now, fields=fields,
            )
            self.db.commit()
            return result
        except PublishIntentBlocked:
            self.db.rollback()
            raise
        except sqlite3.IntegrityError:
            self.db.rollback()
            raise PublishIntentBlocked("intent_duplicate_or_replay") from None
        except Exception:
            self.db.rollback()
            raise PublishIntentBlocked("intent_reservation_failed") from None

    def cancel(
        self, *, key: tuple[str, str, str], operation_id: str,
        expected_intent_version: int,
        verifier: PinnedRS256SessionVerifier | None,
        bearer: str, trusted_issuer: str,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Cancel without external source access; never release duplicate keys."""
        return self._transition(
            key=key, operation_id=operation_id,
            expected_intent_version=expected_intent_version,
            verifier=verifier, bearer=bearer,
            trusted_issuer=trusted_issuer,
            source=None, action="CANCEL", as_of=as_of,
        )

    def recheck(
        self, *, key: tuple[str, str, str], operation_id: str,
        expected_intent_version: int,
        verifier: PinnedRS256SessionVerifier | None,
        bearer: str, trusted_issuer: str,
        source: CanonicalProtectedReviewReader | None,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Recheck the current rights and drift; quarantine permanently if invalid."""
        return self._transition(
            key=key, operation_id=operation_id,
            expected_intent_version=expected_intent_version,
            verifier=verifier, bearer=bearer,
            trusted_issuer=trusted_issuer,
            source=source, action="RECHECK", as_of=as_of,
        )

    def _transition(
        self, *, key: tuple[str, str, str], operation_id: str,
        expected_intent_version: int,
        verifier: PinnedRS256SessionVerifier | None,
        bearer: str, trusted_issuer: str,
        source: CanonicalProtectedReviewReader | None,
        action: str, as_of: datetime | None,
    ) -> dict[str, Any]:
        _database(self.db)
        key = _key(*key)
        if (not isinstance(operation_id, str) or OP_ID.fullmatch(operation_id) is None
                or type(expected_intent_version) is not int or expected_intent_version < 1):
            raise PublishIntentBlocked("intent_operation_invalid")
        now = _utc(as_of or datetime.now(timezone.utc), "intent_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            actor = _actor(
                self.db, verifier=verifier, bearer=bearer,
                issuer=trusted_issuer, key=key, now=now,
            )
            old = _head_row(self.db, key)
            _history(self.db, key, old)
            if old is None or old["version"] != expected_intent_version:
                raise PublishIntentBlocked("intent_version_conflict")
            if old["state"] != "HELD_BLOCKED":
                raise PublishIntentBlocked("intent_already_terminal")
            if self.db.execute(
                "SELECT 1 FROM sns_media_publish_intent_events WHERE operation_id=?",
                (operation_id,),
            ).fetchone():
                raise PublishIntentBlocked("intent_operation_replayed")
            reason = "operator_cancelled"
            if action == "RECHECK":
                reason = "source_unavailable"
                try:
                    context = _source(self.db, source, key)
                    fields = _preflight(
                        self.db, key, context,
                        old["binding_version"], old["review_version"], now,
                    )
                    if any(fields[name] != old[name] for name in (
                        "queue_sha256", "context_sha256", "content_sha256",
                        "media_asset_id", "source_id", "review_event_sha256",
                        "binding_event_sha256",
                    )):
                        reason = "queue_drift"
                    elif _time(old["held_until"], "intent_expiration_invalid") <= now:
                        reason = "reservation_expired"
                    else:
                        self.db.commit()
                        return {
                            "status": "HELD_BLOCKED", "source_rechecked": True,
                            "intent_version": old["version"],
                            "effective_approval": False,
                            "publish_authorized": False,
                            "ready_transitions_performed": False,
                            "external_queue_atomicity_guaranteed": False,
                            "publish_attempted": False,
                        }
                except PublishIntentBlocked as exc:
                    reason = (
                        "source_unavailable"
                        if str(exc) == "intent_trusted_source_unavailable"
                        else "rights_or_review_invalid"
                    )
                action = "QUARANTINE"
            fields = {name: old[name] for name in (
                "queue_sha256", "context_sha256", "content_sha256",
                "media_asset_id", "source_id", "review_version",
                "review_event_sha256", "binding_version",
                "binding_event_sha256", "held_until",
            )}
            result = _append(
                self.db, key, old=old, action=action, operation_id=operation_id,
                actor=actor, reason=reason, now=now, fields=fields,
            )
            self.db.commit()
            return result
        except PublishIntentBlocked:
            self.db.rollback()
            raise
        except sqlite3.Error:
            self.db.rollback()
            raise PublishIntentBlocked("intent_transition_failed") from None
        except Exception:
            self.db.rollback()
            raise PublishIntentBlocked("intent_transition_failed") from None

    def inspect(self, *, key: tuple[str, str, str]) -> dict[str, Any]:
        """Read-only audit; a stored HOLD is always BLOCKED."""
        _database(self.db)
        key = _key(*key)
        try:
            head = _head_row(self.db, key)
            _history(self.db, key, head)
        except sqlite3.Error:
            raise PublishIntentBlocked("intent_inspection_failed") from None
        return {
            "status": head["state"] if head else "NO_INTENT",
            "intent_version": head["version"] if head else 0,
            "event_sha256": head["last_event_sha256"] if head else ZERO,
            "effective_approval": False, "publish_authorized": False,
            "external_queue_atomicity_guaranteed": False,
        }
