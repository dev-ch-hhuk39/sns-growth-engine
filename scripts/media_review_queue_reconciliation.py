#!/usr/bin/env python3
"""Phase 5B-5C: atomic local review/queue binding and fail-closed reconciliation.

This module NEVER changes external Google Sheets, READY, or a publisher.
A Sheets read and a SQLite commit are not an atomic cross-system transaction.
All states herein remain blocked; 5B-6 must separately enforce publish-time
authority and prohibit the legacy bypass paths before any real approval.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from build_media_human_review_plan import MEDIA_SLOTS
from build_media_review_approval_receipts import (
    QUEUE_ID_RE, _sha256, _validate_history, _validate_plan,
)
from media_review_transactional_ledger import _head, _validate_event_history
from media_review_trusted_precommit import (
    CanonicalReviewContext, CanonicalReviewReader,
    ReviewRequest, _time, _utc, _verify_evidence, _verify_queue,
)

MIGRATION = Path(__file__).resolve().parents[1] / "db" / "migrations" / "0003_sns_media_review_queue_reconciliation.sql"
ZERO = "0" * 64
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
OP_RE = re.compile(r"(?:op|sync)_[A-Za-z0-9_.:-]{12,110}\Z")
MAX_EVENTS = 512
MAX_SNAPSHOT_BYTES = 256 * 1024
SCHEMA = "sns_review_queue_reconciliation_v1"
ACTIONS = frozenset({
    "REVIEW_BOUND", "REVIEW_REVOKED", "SOURCE_MATCH",
    "SOURCE_DRIFT", "SOURCE_UNAVAILABLE",
})
EVENT_FIELDS = frozenset({
    "schema_version", "operation_id", "account_id", "slot_id", "queue_id",
    "binding_version", "action", "queue_revision", "queue_sha256",
    "context_sha256",
    "ledger_version", "ledger_event_sha256", "state",
    "reconciliation_state", "observed_revision", "observed_sha256",
    "created_at", "previous_event_sha256",
})
STATES = frozenset({
    "REVIEW_RECORDED_BLOCKED", "REVOKED_BLOCKED", "DRIFT_QUARANTINED",
})
RECON_STATES = frozenset({"PENDING", "MATCHED_BLOCKED", "CONFLICT_BLOCKED"})


class QueueReconciliationBlocked(ValueError):
    """Public-safe reason code, never private queue rows or provider exceptions."""


def initialize_reconciliation_schema(db: sqlite3.Connection) -> None:
    """Explicit migration on a dedicated review DB, never at request time."""
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise QueueReconciliationBlocked("queue_migration_requires_autocommit")
    try:
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sns_media_review_heads'"
        ).fetchone() is None:
            raise QueueReconciliationBlocked("review_ledger_migration_required")
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
        db.execute("PRAGMA foreign_keys = ON")
    except (sqlite3.Error, OSError):
        raise QueueReconciliationBlocked("queue_migration_failed") from None


def _canon(value: dict[str, Any]) -> str:
    try:
        encoded = json.dumps(
            value, sort_keys=True, ensure_ascii=True, allow_nan=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, OverflowError):
        raise QueueReconciliationBlocked("queue_snapshot_invalid") from None
    if len(encoded) > MAX_SNAPSHOT_BYTES:
        raise QueueReconciliationBlocked("queue_snapshot_too_large")
    return encoded


def _hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canon(value).encode("ascii")).hexdigest()


def queue_fingerprint(queue: dict[str, Any]) -> str:
    """Complete row digest: any changed field (including captions) invalidates."""
    if not isinstance(queue, dict):
        raise QueueReconciliationBlocked("queue_snapshot_invalid")
    return _hash(queue)


def context_fingerprint(context: CanonicalReviewContext) -> str:
    """Bind plan, full draft history and original-proof metadata as one digest."""
    if not isinstance(context, CanonicalReviewContext):
        raise QueueReconciliationBlocked("review_context_invalid")
    try:
        return _hash({
            "plan": context.plan, "receipts": context.receipts,
            "evidence": dict(context.evidence_by_id),
        })
    except (TypeError, ValueError, OverflowError):
        raise QueueReconciliationBlocked("review_context_invalid") from None


def _ensure_db(db: sqlite3.Connection, *, must_be_in_transaction: bool) -> None:
    try:
        if (not isinstance(db, sqlite3.Connection)
                or db.in_transaction is not must_be_in_transaction
                or db.execute("PRAGMA foreign_keys").fetchone()[0] != 1):
            raise QueueReconciliationBlocked("queue_database_unavailable")
    except sqlite3.Error:
        raise QueueReconciliationBlocked("queue_database_unavailable") from None


def _key(account_id: str, slot_id: str, queue_id: str) -> tuple[str, str, str]:
    if (not isinstance(account_id, str)
            or not isinstance(slot_id, str)
            or (account_id, slot_id) not in MEDIA_SLOTS
            or not isinstance(queue_id, str)
            or QUEUE_ID_RE.fullmatch(queue_id) is None):
        raise QueueReconciliationBlocked("queue_candidate_invalid")
    return account_id, slot_id, queue_id


def _op(operation_id: str) -> None:
    if not isinstance(operation_id, str) or OP_RE.fullmatch(operation_id) is None:
        raise QueueReconciliationBlocked("queue_operation_invalid")


def _row(db: sqlite3.Connection, key: tuple[str, str, str]) -> dict[str, Any] | None:
    found = db.execute(
        """SELECT queue_revision,queue_sha256,context_sha256,ledger_version,
                  ledger_event_sha256,state,reconciliation_state,
                  binding_version,last_event_sha256,updated_at
           FROM sns_media_review_queue_bindings
           WHERE account_id=? AND slot_id=? AND queue_id=?""", key,
    ).fetchone()
    if found is None:
        return None
    return dict(zip((
        "queue_revision", "queue_sha256", "context_sha256", "ledger_version",
        "ledger_event_sha256", "state", "reconciliation_state",
        "binding_version", "last_event_sha256", "updated_at",
    ), found))


def _verify_history(
    db: sqlite3.Connection, key: tuple[str, str, str], row: dict[str, Any] | None,
) -> None:
    events = db.execute(
        """SELECT operation_id,binding_version,action,
                  previous_event_sha256,event_sha256,payload_json
           FROM sns_media_review_queue_reconciliation_events
           WHERE account_id=? AND slot_id=? AND queue_id=?
           ORDER BY binding_version""", key,
    ).fetchall()
    if row is None:
        if events:
            raise QueueReconciliationBlocked("queue_binding_missing")
        return
    if (len(events) != row["binding_version"]
            or len(events) > MAX_EVENTS
            or row["state"] not in STATES
            or row["reconciliation_state"] not in RECON_STATES):
        raise QueueReconciliationBlocked("queue_binding_history_invalid")
    previous = ZERO
    last = None
    for sequence, (operation, version, action, prev, event_hash, raw) in enumerate(events, 1):
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            raise QueueReconciliationBlocked("queue_binding_history_invalid") from None
        if (not isinstance(payload, dict) or set(payload) != EVENT_FIELDS
                or payload.get("schema_version") != SCHEMA
                or payload.get("operation_id") != operation
                or payload.get("binding_version") != version
                or version != sequence or action not in ACTIONS
                or payload.get("action") != action
                or tuple(payload.get(name) for name in ("account_id","slot_id","queue_id")) != key
                or prev != previous or payload.get("previous_event_sha256") != prev
                or _hash(payload) != event_hash):
            raise QueueReconciliationBlocked("queue_binding_history_tampered")
        previous, last = event_hash, payload
    if last is None or any((
        row["queue_revision"] != last["queue_revision"],
        row["queue_sha256"] != last["queue_sha256"],
        row["context_sha256"] != last["context_sha256"],
        row["ledger_version"] != last["ledger_version"],
        row["ledger_event_sha256"] != last["ledger_event_sha256"],
        row["state"] != last["state"],
        row["reconciliation_state"] != last["reconciliation_state"],
        row["last_event_sha256"] != previous,
        row["updated_at"] != last["created_at"],
    )):
        raise QueueReconciliationBlocked("queue_binding_head_tampered")


def _append_event(
    db: sqlite3.Connection, key: tuple[str, str, str],
    old: dict[str, Any] | None, *,
    operation_id: str,
    action: str,
    queue_revision: str,
    queue_sha256: str,
    context_sha256: str,
    ledger_version: int,
    ledger_event_sha256: str,
    state: str,
    reconciliation_state: str,
    observed_revision: str,
    observed_sha256: str,
    now: datetime,
) -> int:
    _op(operation_id)
    if (action not in ACTIONS or state not in STATES
            or reconciliation_state not in RECON_STATES
            or not isinstance(queue_revision, str) or not queue_revision
            or not SHA256_RE.fullmatch(queue_sha256)
            or not SHA256_RE.fullmatch(context_sha256)
            or not SHA256_RE.fullmatch(ledger_event_sha256)
            or type(ledger_version) is not int or ledger_version < 1
            or not isinstance(observed_revision, str)
            or not SHA256_RE.fullmatch(observed_sha256)):
        raise QueueReconciliationBlocked("queue_binding_invalid")
    sequence = (old["binding_version"] if old else 0) + 1
    if sequence > MAX_EVENTS:
        raise QueueReconciliationBlocked("queue_binding_at_capacity")
    if db.execute(
        "SELECT 1 FROM sns_media_review_queue_reconciliation_events WHERE operation_id=?",
        (operation_id,),
    ).fetchone():
        raise QueueReconciliationBlocked("queue_operation_replayed")
    previous = old["last_event_sha256"] if old else ZERO
    payload = {
        "schema_version": SCHEMA, "operation_id": operation_id,
        "account_id": key[0], "slot_id": key[1], "queue_id": key[2],
        "binding_version": sequence, "action": action,
        "queue_revision": queue_revision, "queue_sha256": queue_sha256,
        "context_sha256": context_sha256,
        "ledger_version": ledger_version, "ledger_event_sha256": ledger_event_sha256,
        "state": state, "reconciliation_state": reconciliation_state,
        "observed_revision": observed_revision, "observed_sha256": observed_sha256,
        "created_at": now.isoformat(timespec="seconds"),
        "previous_event_sha256": previous,
    }
    digest = _hash(payload)
    data = (
        queue_revision, queue_sha256, context_sha256, ledger_version, ledger_event_sha256,
        state, reconciliation_state, sequence, digest, payload["created_at"],
    )
    if old is None:
        db.execute(
            """INSERT INTO sns_media_review_queue_bindings
               (account_id,slot_id,queue_id,queue_revision,queue_sha256,context_sha256,
                ledger_version,ledger_event_sha256,state,reconciliation_state,
                binding_version,last_event_sha256,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (*key, *data),
        )
    else:
        result = db.execute(
            """UPDATE sns_media_review_queue_bindings
               SET queue_revision=?,queue_sha256=?,context_sha256=?,ledger_version=?,
                   ledger_event_sha256=?,state=?,reconciliation_state=?,
                   binding_version=?,last_event_sha256=?,updated_at=?
               WHERE account_id=? AND slot_id=? AND queue_id=?
                 AND binding_version=? AND last_event_sha256=?""",
            (*data, *key, old["binding_version"], old["last_event_sha256"]),
        )
        if result.rowcount != 1:
            raise QueueReconciliationBlocked("queue_binding_version_conflict")
    db.execute(
        """INSERT INTO sns_media_review_queue_reconciliation_events
           (operation_id,account_id,slot_id,queue_id,binding_version,action,
            previous_event_sha256,event_sha256,payload_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            operation_id, *key, sequence, action,
            previous, digest, _canon(payload),
        ),
    )
    return sequence


def _current_review_still_valid(
    db: sqlite3.Connection, key: tuple[str, str, str],
    bound: dict[str, Any], context: CanonicalReviewContext, now: datetime,
) -> bool:
    """Revalidate queue, draft chain and rights WITHOUT self-issued identity.

    This is a read-only safety test, not a new approval. A missing/expired
    source, permission, original proof or changed payload fails closed.
    """
    try:
        if (not isinstance(context, CanonicalReviewContext)
                or context_fingerprint(context) != bound["context_sha256"]):
            return False
        record = db.execute(
            """SELECT payload_json FROM sns_media_review_events
               WHERE account_id=? AND slot_id=? AND queue_id=?
                 AND sequence=?""",
            (*key, bound["ledger_version"]),
        ).fetchone()
        if record is None:
            return False
        event = json.loads(record[0])
        if (event.get("action") != "REVIEW_RECORD"
                or _time(event.get("rights_expire_at"), "rights_expired") <= now):
            return False
        request = ReviewRequest(
            account_id=key[0], slot_id=key[1], queue_id=key[2],
            expected_queue_revision=bound["queue_revision"],
            expected_plan_sha256=event["source_plan_sha256"],
            expected_receipts_head_sha256=event["receipts_head_sha256"],
            draft_event_sha256=event["draft_event_sha256"],
            confirm_human_review=True,
            expected_queue_sha256=bound["queue_sha256"],
        )
        queue = _verify_queue(context.queue, request)
        plan = _validate_plan(context.plan)
        if _sha256(context.plan) != request.expected_plan_sha256:
            return False
        events, latest_receipt_head = _validate_history(
            context.receipts, request.expected_plan_sha256, plan,
        )
        if latest_receipt_head != request.expected_receipts_head_sha256:
            return False
        matching = [
            item for item in events
            if (item["account_id"], item["slot_id"], item["queue_id"]) == key
        ]
        if (not matching or matching[-1]["decision"] != "APPROVE"
                or matching[-1]["event_sha256"] != request.draft_event_sha256
                or matching[-1]["reviewer_id"] != event["reviewer_subject"]):
            return False
        _verify_evidence(matching[-1], queue, context.evidence_by_id, now)
        return True
    except Exception:
        # Never expose raw data or trusted provider exceptions in diagnostics.
        return False


class ReviewQueueReconciliation:
    """Opt-in transactional companion for the existing SQLite review ledger."""

    def __init__(self, db: sqlite3.Connection) -> None:
        if not isinstance(db, sqlite3.Connection):
            raise QueueReconciliationBlocked("queue_database_unavailable")
        self.db = db

    def bind_recorded_review(
        self, *, key: tuple[str, str, str], operation_id: str,
        preflight: dict[str, Any], expected_queue_sha256: str | None,
        ledger_version: int, ledger_event_sha256: str, now: datetime,
    ) -> None:
        """Called AFTER _append() but BEFORE ledger commit, sharing one transaction."""
        _ensure_db(self.db, must_be_in_transaction=True)
        key = _key(*key)
        old = _row(self.db, key)
        _verify_history(self.db, key, old)
        if old is not None and old["state"] != "REVOKED_BLOCKED":
            raise QueueReconciliationBlocked("prior_review_not_released")
        fingerprint = preflight.get("canonical_queue_sha256")
        context_digest = preflight.get("canonical_context_sha256")
        if (preflight.get("status") != "PRECOMMIT_CHECKS_PASSED_NO_APPROVAL"
                or preflight.get("queue_revision") is None
                or preflight.get("effective_approval") is not False
                or not isinstance(fingerprint, str)
                or SHA256_RE.fullmatch(fingerprint) is None
                or expected_queue_sha256 != fingerprint
                or not isinstance(context_digest, str)
                or SHA256_RE.fullmatch(context_digest) is None):
            raise QueueReconciliationBlocked("queue_precommit_binding_invalid")
        head = _head(self.db, key)
        _validate_event_history(self.db, key, head)
        if (head["version"] != ledger_version
                or head["hash"] != ledger_event_sha256
                or head["state"] != "REVIEW_RECORDED_ONLY"
                or head["queue_revision"] != preflight["queue_revision"]):
            raise QueueReconciliationBlocked("queue_ledger_binding_invalid")
        _append_event(
            self.db, key, old, operation_id=operation_id,
            action="REVIEW_BOUND", queue_revision=preflight["queue_revision"],
            queue_sha256=fingerprint, context_sha256=context_digest,
            ledger_version=ledger_version,
            ledger_event_sha256=ledger_event_sha256,
            state="REVIEW_RECORDED_BLOCKED", reconciliation_state="PENDING",
            observed_revision=preflight["queue_revision"],
            observed_sha256=fingerprint, now=now,
        )

    def bind_revocation(
        self, *, key: tuple[str, str, str], operation_id: str,
        queue_revision: str, ledger_version: int,
        ledger_event_sha256: str, now: datetime,
    ) -> None:
        """Cancellation always keeps a block, even with missing external queue."""
        _ensure_db(self.db, must_be_in_transaction=True)
        key = _key(*key)
        old = _row(self.db, key)
        _verify_history(self.db, key, old)
        head = _head(self.db, key)
        _validate_event_history(self.db, key, head)
        if (head["version"] != ledger_version
                or head["hash"] != ledger_event_sha256
                or head["state"] != "REVOKED"):
            raise QueueReconciliationBlocked("queue_revocation_binding_invalid")
        _append_event(
            self.db, key, old, operation_id=operation_id,
            action="REVIEW_REVOKED",
            queue_revision=queue_revision,
            queue_sha256=old["queue_sha256"] if old else ZERO,
            context_sha256=old["context_sha256"] if old else ZERO,
            ledger_version=ledger_version,
            ledger_event_sha256=ledger_event_sha256,
            state="REVOKED_BLOCKED", reconciliation_state="CONFLICT_BLOCKED",
            observed_revision="", observed_sha256=ZERO, now=now,
        )

    def reconcile_once(
        self, *, key: tuple[str, str, str],
        source: CanonicalReviewReader | None,
        operation_id: str, expected_binding_version: int,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Recheck a trusted backend snapshot and quarantine on any uncertainty.

        No access to an external queue writer is provided. A successful match
        is merely a historical read comparison, never a publish authorization.
        """
        _ensure_db(self.db, must_be_in_transaction=False)
        key = _key(*key)
        _op(operation_id)
        if type(expected_binding_version) is not int or expected_binding_version < 1:
            raise QueueReconciliationBlocked("queue_expected_version_invalid")
        now = _utc(as_of or datetime.now(timezone.utc), "queue_clock_invalid")
        observed_revision = ""
        observed_fingerprint = ZERO
        observed_context_digest = ZERO
        available = False
        if source is not None:
            try:
                context = source.load_current(*key)
                queue = context.queue
                if isinstance(queue, dict):
                    observed_revision = queue.get("revision", "")
                    if not isinstance(observed_revision, str):
                        observed_revision = ""
                    observed_fingerprint = queue_fingerprint(queue)
                    observed_context_digest = context_fingerprint(context)
                    available = True
            except Exception:
                available = False
        try:
            self.db.execute("BEGIN IMMEDIATE")
            old = _row(self.db, key)
            _verify_history(self.db, key, old)
            if old is None:
                raise QueueReconciliationBlocked("queue_binding_missing")
            if old["binding_version"] != expected_binding_version:
                raise QueueReconciliationBlocked("queue_binding_version_conflict")
            if old["state"] != "REVIEW_RECORDED_BLOCKED":
                raise QueueReconciliationBlocked("queue_already_blocked")
            head = _head(self.db, key)
            _validate_event_history(self.db, key, head)
            ledger_ok = (
                head["version"] == old["ledger_version"]
                and head["hash"] == old["ledger_event_sha256"]
                and head["state"] == "REVIEW_RECORDED_ONLY"
            )
            matches = (
                available and ledger_ok
                and observed_revision == old["queue_revision"]
                and observed_fingerprint == old["queue_sha256"]
                and observed_context_digest == old["context_sha256"]
                and _current_review_still_valid(self.db, key, old, context, now)
            )
            # Repeated, unchanged successful polling must not exhaust the
            # 512-event append-only journal. New mismatches always append.
            if self.db.execute(
                "SELECT 1 FROM sns_media_review_queue_reconciliation_events WHERE operation_id=?",
                (operation_id,),
            ).fetchone():
                raise QueueReconciliationBlocked("queue_operation_replayed")
            if matches and old["reconciliation_state"] == "MATCHED_BLOCKED":
                self.db.commit()
                return {
                    "status": "MATCHED_BLOCKED",
                    "binding_version": old["binding_version"],
                    "source_matched_at_check": True,
                    "quarantined": False,
                    "effective_approval": False,
                    "ready_transitions_performed": False,
                    "external_queue_atomicity_guaranteed": False,
                    "publish_authorized": False,
                }
            action = (
                "SOURCE_MATCH" if matches
                else "SOURCE_DRIFT" if available
                else "SOURCE_UNAVAILABLE"
            )
            state = "REVIEW_RECORDED_BLOCKED" if matches else "DRIFT_QUARANTINED"
            reconciliation = "MATCHED_BLOCKED" if matches else "CONFLICT_BLOCKED"
            version = _append_event(
                self.db, key, old, operation_id=operation_id, action=action,
                queue_revision=old["queue_revision"],
                queue_sha256=old["queue_sha256"],
                context_sha256=old["context_sha256"],
                ledger_version=old["ledger_version"],
                ledger_event_sha256=old["ledger_event_sha256"],
                state=state, reconciliation_state=reconciliation,
                observed_revision=observed_revision,
                observed_sha256=observed_fingerprint, now=now,
            )
            self.db.commit()
        except QueueReconciliationBlocked:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise QueueReconciliationBlocked("queue_reconciliation_storage_failed") from None
        return {
            "status": reconciliation,
            "binding_version": version,
            "source_matched_at_check": matches,
            "quarantined": not matches,
            "effective_approval": False,
            "ready_transitions_performed": False,
            "external_queue_atomicity_guaranteed": False,
            "publish_authorized": False,
        }

    def barrier(self, *key: str) -> dict[str, Any]:
        """Non-authorizing diagnostic. No code path in this phase can publish."""
        _ensure_db(self.db, must_be_in_transaction=False)
        validated = _key(*key)
        try:
            row = _row(self.db, validated)
            _verify_history(self.db, validated, row)
            if row is not None:
                head = _head(self.db, validated)
                _validate_event_history(self.db, validated, head)
                expected_head_state = (
                    "REVOKED" if row["state"] == "REVOKED_BLOCKED"
                    else "REVIEW_RECORDED_ONLY"
                )
                if (head["version"] != row["ledger_version"]
                        or head["hash"] != row["ledger_event_sha256"]
                        or head["state"] != expected_head_state):
                    return {
                        "state": "LEDGER_DIVERGENCE_BLOCKED",
                        "reconciliation_state": "CONFLICT_BLOCKED",
                        "binding_version": row["binding_version"],
                        "effective_approval": False,
                        "publish_authorized": False,
                        "external_queue_atomicity_guaranteed": False,
                    }
        except sqlite3.Error:
            raise QueueReconciliationBlocked("queue_reconciliation_storage_failed") from None
        return {
            "state": row["state"] if row else "NO_BINDING",
            "reconciliation_state": row["reconciliation_state"] if row else "NO_BINDING",
            "binding_version": row["binding_version"] if row else 0,
            "effective_approval": False,
            "publish_authorized": False,
            "external_queue_atomicity_guaranteed": False,
        }

    def pending_candidates(self) -> list[tuple[str, str, str, int]]:
        """Pending or previously matched items needing recurring rechecks."""
        _ensure_db(self.db, must_be_in_transaction=False)
        try:
            rows = self.db.execute(
                """SELECT account_id,slot_id,queue_id,binding_version
                   FROM sns_media_review_queue_bindings
                   WHERE state='REVIEW_RECORDED_BLOCKED'
                     AND reconciliation_state IN ('PENDING','MATCHED_BLOCKED')
                   ORDER BY updated_at LIMIT 100""",
            ).fetchall()
        except sqlite3.Error:
            raise QueueReconciliationBlocked("queue_reconciliation_storage_failed") from None
        return [tuple(row) for row in rows]
