#!/usr/bin/env python3
"""Atomic, isolated media-review ledger. Never updates Sheets READY or publishers.

Only a caller running inside a trusted backend with a real token verifier and
canonical evidence reader can record a review; there are deliberately no
production adapters, web endpoint, or CLI to fabricate identities or evidence.

The SQLite transaction is atomic for THIS ledger only. It cannot give atomic
consistency with an external Google Sheets queue. Recorded reviews are never
effective publish permission, even if the precommit check passes.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from media_review_trusted_precommit import (
    CanonicalReviewReader,
    PrecommitBlocked,
    ReviewRequest,
    SessionVerifier,
    _check_principal,
    _check_request,
    _utc,
    evaluate_precommit,
)

MIGRATION_PATH = Path(__file__).resolve().parents[1] / "db" / "migrations" / "0001_sns_media_review_ledger.sql"
ZERO = "0" * 64
OP_ID = re.compile(r"op_[A-Za-z0-9_.:-]{12,110}\Z")
MAX_EVENT_COUNT = 512
PAYLOAD_SCHEMA = "sns_review_ledger_event_v1"
REVOKE_REASONS = frozenset({
    "consent_withdrawn", "rights_expired", "evidence_missing",
    "quality_failed", "review_reopened", "source_mismatch",
})
EVENT_FIELDS = frozenset({
    "schema_version", "operation_id", "account_id", "slot_id", "queue_id",
    "sequence", "action", "reviewer_subject", "created_at", "reason_code",
    "queue_revision", "draft_event_sha256", "source_plan_sha256",
    "receipts_head_sha256", "rights_expire_at", "previous_event_sha256",
})


class ReviewLedgerBlocked(ValueError):
    """Only stable reason codes. Do not expose SQLite/provider exception text."""


def initialize_review_schema(connection: sqlite3.Connection) -> None:
    """Explicit developer/admin migration: never invoked during a write call."""
    if connection.in_transaction:
        raise ReviewLedgerBlocked("migration_requires_autocommit")
    connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))
    connection.execute("PRAGMA foreign_keys = ON")


def _canon(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False)


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _require_op(operation_id: str, expected_version: int) -> None:
    if (not isinstance(operation_id, str) or not OP_ID.fullmatch(operation_id)
            or type(expected_version) is not int or expected_version < 0
            or expected_version > MAX_EVENT_COUNT):
        raise ReviewLedgerBlocked("operation_identity_invalid")


def _ensure_db(connection: sqlite3.Connection) -> None:
    if (not isinstance(connection, sqlite3.Connection)
            or connection.in_transaction
            or connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1):
        raise ReviewLedgerBlocked("review_database_unavailable")


def _head(connection: sqlite3.Connection, key: tuple[str, str, str]) -> dict[str, Any]:
    row = connection.execute(
        """SELECT ledger_version,review_state,last_event_sha256,
                  last_draft_event_sha256,last_queue_revision
           FROM sns_media_review_heads
           WHERE account_id=? AND slot_id=? AND queue_id=?""", key,
    ).fetchone()
    if row is None:
        return {
            "version": 0, "state": "NONE", "hash": ZERO,
            "draft": "", "queue_revision": "",
        }
    return {
        "version": row[0], "state": row[1], "hash": row[2],
        "draft": row[3], "queue_revision": row[4],
    }


def _validate_event_history(
    connection: sqlite3.Connection, key: tuple[str, str, str], head: dict[str, Any],
) -> None:
    rows = connection.execute(
        """SELECT sequence,action,operation_id,previous_event_sha256,
                  event_sha256,payload_json
           FROM sns_media_review_events
           WHERE account_id=? AND slot_id=? AND queue_id=?
           ORDER BY sequence""", key,
    ).fetchall()
    if len(rows) > MAX_EVENT_COUNT or head["version"] != len(rows):
        raise ReviewLedgerBlocked("review_history_version_invalid")
    last_hash = ZERO
    state = "NONE"
    last_draft = ""
    last_queue_revision = ""
    for index, (sequence, action, op, previous, digest, raw) in enumerate(rows, 1):
        try:
            event = json.loads(raw)
        except (TypeError, ValueError):
            raise ReviewLedgerBlocked("review_history_corrupt") from None
        if (not isinstance(event, dict) or set(event) != EVENT_FIELDS
                or event.get("schema_version") != PAYLOAD_SCHEMA
                or event.get("sequence") != index
                or event.get("operation_id") != op
                or event.get("action") != action
                or (event.get("account_id"), event.get("slot_id"), event.get("queue_id")) != key
                or event.get("previous_event_sha256") != previous
                or previous != last_hash or digest != _digest(event)):
            raise ReviewLedgerBlocked("review_history_tampered")
        if action == "REVIEW_RECORD":
            if state == "REVIEW_RECORDED_ONLY":
                raise ReviewLedgerBlocked("review_history_state_invalid")
            state = "REVIEW_RECORDED_ONLY"
        elif action == "REVOKE" and state == "REVIEW_RECORDED_ONLY":
            state = "REVOKED"
        else:
            raise ReviewLedgerBlocked("review_history_state_invalid")
        last_hash = digest
        last_draft = event["draft_event_sha256"]
        last_queue_revision = event["queue_revision"]
    if (head["hash"] != last_hash or head["state"] != state
            or head["draft"] != last_draft
            or head["queue_revision"] != last_queue_revision):
        raise ReviewLedgerBlocked("review_history_head_invalid")


def _event(
    operation_id: str, key: tuple[str, str, str], head: dict[str, Any],
    *,
    action: str,
    reviewer_subject: str,
    created_at: datetime,
    reason_code: str,
    queue_revision: str,
    draft_event_sha256: str,
    source_plan_sha256: str,
    receipts_head_sha256: str,
    rights_expire_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": PAYLOAD_SCHEMA, "operation_id": operation_id,
        "account_id": key[0], "slot_id": key[1], "queue_id": key[2],
        "sequence": head["version"] + 1, "action": action,
        "reviewer_subject": reviewer_subject,
        "created_at": created_at.isoformat(timespec="seconds"),
        "reason_code": reason_code,
        "queue_revision": queue_revision,
        "draft_event_sha256": draft_event_sha256,
        "source_plan_sha256": source_plan_sha256,
        "receipts_head_sha256": receipts_head_sha256,
        "rights_expire_at": rights_expire_at,
        "previous_event_sha256": head["hash"],
    }


def _append(
    connection: sqlite3.Connection, key: tuple[str, str, str],
    head: dict[str, Any], event: dict[str, Any], state: str,
) -> tuple[int, str]:
    digest = _digest(event)
    version = head["version"] + 1
    connection.execute(
        """INSERT INTO sns_media_review_events
           (operation_id,account_id,slot_id,queue_id,sequence,action,
            previous_event_sha256,event_sha256,payload_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (
            event["operation_id"], *key, version, event["action"],
            head["hash"], digest, _canon(event),
        ),
    )
    updated = connection.execute(
        """UPDATE sns_media_review_heads
           SET ledger_version=?,review_state=?,last_event_sha256=?,
               last_draft_event_sha256=?,last_queue_revision=?,updated_at=?
           WHERE account_id=? AND slot_id=? AND queue_id=?
             AND ledger_version=? AND last_event_sha256=?""",
        (
            version, state, digest, event["draft_event_sha256"],
            event["queue_revision"], event["created_at"],
            *key, head["version"], head["hash"],
        ),
    )
    if updated.rowcount != 1:
        raise ReviewLedgerBlocked("review_head_concurrent_change")
    return version, digest


def _result(
    action: str, key: tuple[str, str, str], version: int, digest: str,
) -> dict[str, Any]:
    return {
        "status": "ISOLATED_REVIEW_LEDGER_RECORDED_NOT_AUTHORIZED",
        "action": action,
        "account_id": key[0], "slot_id": key[1], "queue_id": key[2],
        "ledger_version": version, "last_event_sha256": digest,
        "review_record_persisted": True,
        "authenticated_approval_integrated": False,
        "external_queue_atomicity_guaranteed": False,
        "requires_authoritative_queue_reconciliation": True,
        "requires_publish_time_revalidation": True,
        "effective_approval": False,
        "ready_transitions_performed": False,
        "publish_authorized": False,
    }


def record_review(
    connection: sqlite3.Connection,
    request: ReviewRequest,
    bearer_token: str,
    *,
    verifier: SessionVerifier | None,
    canonical: CanonicalReviewReader | None,
    trusted_issuer: str,
    operation_id: str,
    expected_ledger_version: int,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Append a review decision in one DB transaction, never promote READY.

    The token verifier and canonical reader must be installed by a trusted
    service. The isolated ledger cannot certify external Sheets state.
    """
    now = _utc(as_of or datetime.now(timezone.utc), "review_clock_invalid")
    _check_request(request)
    _require_op(operation_id, expected_ledger_version)
    _ensure_db(connection)
    key = request.account_id, request.slot_id, request.queue_id
    try:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute(
            "SELECT 1 FROM sns_media_review_events WHERE operation_id=?", (operation_id,),
        ).fetchone():
            raise ReviewLedgerBlocked("operation_replayed")
        head = _head(connection, key)
        _validate_event_history(connection, key, head)
        if head["version"] != expected_ledger_version:
            raise ReviewLedgerBlocked("review_version_conflict")
        if head["version"] >= MAX_EVENT_COUNT:
            raise ReviewLedgerBlocked("review_history_at_capacity")
        if head["state"] == "REVIEW_RECORDED_ONLY":
            raise ReviewLedgerBlocked("review_already_recorded")
        if head["state"] == "REVOKED" and head["draft"] == request.draft_event_sha256:
            raise ReviewLedgerBlocked("revoked_draft_cannot_be_reused")
        preflight = evaluate_precommit(
            request, bearer_token, verifier=verifier, canonical=canonical,
            trusted_issuer=trusted_issuer, as_of=now,
        )
        if preflight.get("status") != "PRECOMMIT_CHECKS_PASSED_NO_APPROVAL":
            raise ReviewLedgerBlocked("unexpected_precommit_result")
        # The insert and head CAS share the same SQLite transaction.
        if head["version"] == 0:
            connection.execute(
                """INSERT INTO sns_media_review_heads
                   (account_id,slot_id,queue_id) VALUES (?,?,?)""", key,
            )
        payload = _event(
            operation_id, key, head, action="REVIEW_RECORD",
            reviewer_subject=preflight["session_subject"], created_at=now,
            reason_code="", queue_revision=request.expected_queue_revision,
            draft_event_sha256=request.draft_event_sha256,
            source_plan_sha256=request.expected_plan_sha256,
            receipts_head_sha256=request.expected_receipts_head_sha256,
            rights_expire_at=preflight["rights_recheck_due_before"],
        )
        version, digest = _append(
            connection, key, head, payload, "REVIEW_RECORDED_ONLY",
        )
        connection.commit()
    except (ReviewLedgerBlocked, PrecommitBlocked) as exc:
        connection.rollback()
        raise ReviewLedgerBlocked(
            str(exc) if isinstance(exc, ReviewLedgerBlocked) else "precommit_rejected"
        ) from None
    except sqlite3.Error:
        connection.rollback()
        raise ReviewLedgerBlocked("review_storage_failed") from None
    return _result("REVIEW_RECORD", key, version, digest)


def revoke_review(
    connection: sqlite3.Connection,
    request: ReviewRequest,
    bearer_token: str,
    *,
    verifier: SessionVerifier | None,
    trusted_issuer: str,
    operation_id: str,
    expected_ledger_version: int,
    reason_code: str,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Audited revocation does not need currently valid rights or an OK draft."""
    now = _utc(as_of or datetime.now(timezone.utc), "review_clock_invalid")
    _check_request(request)
    _require_op(operation_id, expected_ledger_version)
    _ensure_db(connection)
    if not isinstance(reason_code, str) or reason_code not in REVOKE_REASONS:
        raise ReviewLedgerBlocked("revocation_reason_invalid")
    if (not verifier or not isinstance(bearer_token, str)
            or not bearer_token.startswith("Bearer ")
            or len(bearer_token) < 16 or len(bearer_token) > 4096
            or len(bearer_token.split()) != 2):
        raise ReviewLedgerBlocked("revocation_session_unavailable")
    try:
        principal = verifier.verify(bearer_token[7:], now=now)
        principal = _check_principal(principal, request, now, trusted_issuer)
    except Exception:
        raise ReviewLedgerBlocked("revocation_authentication_failed") from None
    key = request.account_id, request.slot_id, request.queue_id
    try:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute(
            "SELECT 1 FROM sns_media_review_events WHERE operation_id=?", (operation_id,),
        ).fetchone():
            raise ReviewLedgerBlocked("operation_replayed")
        head = _head(connection, key)
        _validate_event_history(connection, key, head)
        if head["version"] != expected_ledger_version:
            raise ReviewLedgerBlocked("review_version_conflict")
        if head["version"] >= MAX_EVENT_COUNT:
            raise ReviewLedgerBlocked("review_history_at_capacity")
        if head["state"] != "REVIEW_RECORDED_ONLY":
            raise ReviewLedgerBlocked("no_active_record_to_revoke")
        last = connection.execute(
            """SELECT payload_json FROM sns_media_review_events
               WHERE account_id=? AND slot_id=? AND queue_id=?
               AND sequence=?""", (*key, head["version"]),
        ).fetchone()
        if last is None:
            raise ReviewLedgerBlocked("revocation_target_missing")
        previous_payload = json.loads(last[0])
        if (previous_payload["draft_event_sha256"] != request.draft_event_sha256
                or previous_payload["queue_revision"] != request.expected_queue_revision
                or previous_payload["source_plan_sha256"] != request.expected_plan_sha256
                or previous_payload["receipts_head_sha256"] != request.expected_receipts_head_sha256):
            raise ReviewLedgerBlocked("revocation_target_changed")
        payload = _event(
            operation_id, key, head, action="REVOKE",
            reviewer_subject=principal.subject, created_at=now,
            reason_code=reason_code, queue_revision=head["queue_revision"],
            draft_event_sha256=head["draft"],
            source_plan_sha256=request.expected_plan_sha256,
            receipts_head_sha256=request.expected_receipts_head_sha256,
            rights_expire_at=previous_payload["rights_expire_at"],
        )
        version, digest = _append(connection, key, head, payload, "REVOKED")
        connection.commit()
    except ReviewLedgerBlocked as exc:
        connection.rollback()
        raise ReviewLedgerBlocked(str(exc)) from None
    except (sqlite3.Error, ValueError, KeyError, TypeError):
        connection.rollback()
        raise ReviewLedgerBlocked("review_storage_failed") from None
    return _result("REVOKE", key, version, digest)


def verify_ledger_integrity(
    connection: sqlite3.Connection, account_id: str, slot_id: str, queue_id: str,
) -> dict[str, Any]:
    """Read-only integrity report. A hash chain is not a digital signature."""
    _ensure_db(connection)
    key = account_id, slot_id, queue_id
    try:
        head = _head(connection, key)
        _validate_event_history(connection, key, head)
    except sqlite3.Error:
        raise ReviewLedgerBlocked("review_storage_failed") from None
    return {
        "status": "HASH_CHAIN_VALID_NOT_SIGNED",
        "account_id": account_id, "slot_id": slot_id, "queue_id": queue_id,
        "ledger_version": head["version"], "review_state": head["state"],
        "head_sha256": head["hash"],
        "publish_authorized": False, "effective_approval": False,
    }
