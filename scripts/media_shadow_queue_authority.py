#!/usr/bin/env python3
"""Phase 5B-6E: nonauthorizing, same-SQLite shadow queue and reader.

The shadow is seeded exclusively by a trusted, signed-session protected reader.
It can supply plan/receipts/queue to the *existing* review/intent/dispatch
checks within their SQLite transaction. External Sheets is NOT transacted,
changed, polled or automatically reconciled here; source outages, revoked
proofs, drift or an expired observation lease fail closed. Real SNS media
publishing remains unconditionally forbidden by Phase 5B-6A.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from build_media_review_approval_receipts import _sha256, _validate_history, _validate_plan
from media_publish_intent_authority import _actor, _database, _source
from media_review_canonical_adapter import CanonicalProtectedReviewReader
from media_review_protected_evidence import ProtectedEvidenceVault
from media_review_queue_reconciliation import (
    _key, context_fingerprint, queue_fingerprint,
)
from media_review_trusted_precommit import (
    CanonicalReviewContext, ReviewRequest, _time, _utc,
    _verify_evidence, _verify_queue, evaluate_precommit,
)
from media_review_verified_identity import PinnedRS256SessionVerifier

MIGRATION = (Path(__file__).resolve().parents[1] / "db" / "migrations"
             / "0006_sns_media_shadow_queue.sql")
SCHEMA = "sns_shadow_queue_event_v1"
ZERO = "0" * 64
OP_RE = re.compile(r"shadow_[A-Za-z0-9_.:-]{12,110}\Z")
MAX_SNAPSHOT_BYTES = 256 * 1024
MAX_EVENTS = 512
LEASE = timedelta(seconds=90)
CLOCK_SKEW = timedelta(minutes=2)
FIELDS = ("queue_revision", "queue_sha256", "context_sha256", "snapshot_sha256")
HEAD_FIELDS = ("version", "state", *FIELDS, "snapshot_json",
               "last_event_sha256", "updated_at")
EVENT_FIELDS = frozenset((
    "schema_version", "operation_id", "account_id", "slot_id", "queue_id",
    "version", "action", "state", *FIELDS, "observed_sha256",
    "actor", "created_at", "previous_event_sha256",
))
STATES = frozenset(("SHADOW_BLOCKED", "CONFLICT_BLOCKED", "SOURCE_UNAVAILABLE_BLOCKED"))
SENSITIVE_KEYS = re.compile(
    r"(access[_-]?token|refresh[_-]?token|api[_-]?key|password|"
    r"secret|authorization|bearer|cookie|private[_-]?key)", re.I,
)
SECRET_VALUES = re.compile(
    r"(?i)(bearer\s+[A-Za-z0-9_.-]{12,}|"
    r"(?:access_token|api_key|refresh_token|authorization)=)",
)


class ShadowQueueBlocked(ValueError):
    """Only public-safe reason codes; never the underlying private contents."""


def initialize_shadow_queue_schema(db: sqlite3.Connection) -> None:
    """Explicit offline migration on the existing private review SQLite DB."""
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise ShadowQueueBlocked("shadow_migration_requires_autocommit")
    try:
        needed = (
            "sns_media_review_heads", "sns_review_sessions",
            "sns_media_publish_intent_heads", "sns_media_dispatch_heads",
        )
        for table in needed:
            found = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if not found:
                raise ShadowQueueBlocked("shadow_prerequisite_migration_missing")
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
        db.execute("PRAGMA foreign_keys=ON")
    except (sqlite3.Error, OSError):
        raise ShadowQueueBlocked("shadow_migration_failed") from None


def _canon(payload: dict[str, Any]) -> str:
    try:
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        )
    except (ValueError, TypeError, OverflowError):
        raise ShadowQueueBlocked("shadow_snapshot_invalid") from None
    if len(encoded) > MAX_SNAPSHOT_BYTES:
        raise ShadowQueueBlocked("shadow_snapshot_too_large")
    return encoded


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canon(payload).encode("ascii")).hexdigest()


def _safe_payload(value: Any) -> None:
    """Reject credential-shaped data before storing a trusted source snapshot."""
    if isinstance(value, dict):
        for field, item in value.items():
            if not isinstance(field, str) or SENSITIVE_KEYS.search(field):
                raise ShadowQueueBlocked("shadow_sensitive_data_refused")
            _safe_payload(item)
    elif isinstance(value, list):
        for item in value:
            _safe_payload(item)
    elif isinstance(value, str):
        if SECRET_VALUES.search(value):
            raise ShadowQueueBlocked("shadow_sensitive_data_refused")


def _snapshot(context: CanonicalReviewContext) -> tuple[dict[str, Any], dict[str, str]]:
    data = {
        "plan": context.plan, "receipts": context.receipts,
        "queue": context.queue,
    }
    _safe_payload(data)
    encoded = _canon(data)
    return data, {
        "queue_revision": context.queue["revision"],
        "queue_sha256": queue_fingerprint(context.queue),
        "context_sha256": context_fingerprint(context),
        "snapshot_sha256": hashlib.sha256(encoded.encode("ascii")).hexdigest(),
    }


def _row(db: sqlite3.Connection, key: tuple[str, str, str]) -> dict[str, Any] | None:
    record = db.execute(
        "SELECT " + ",".join(HEAD_FIELDS) + """
         FROM sns_media_shadow_queue_heads
         WHERE account_id=? AND slot_id=? AND queue_id=?""", key,
    ).fetchone()
    return dict(zip(HEAD_FIELDS, record)) if record is not None else None


def _history(db: sqlite3.Connection, key: tuple[str, str, str],
             head: dict[str, Any] | None) -> None:
    events = db.execute(
        """SELECT version,action,operation_id,previous_event_sha256,
                  event_sha256,payload_json
           FROM sns_media_shadow_queue_events
           WHERE account_id=? AND slot_id=? AND queue_id=?
           ORDER BY version""", key,
    ).fetchall()
    if head is None:
        if events:
            raise ShadowQueueBlocked("shadow_orphan_events")
        return
    if (head["state"] not in STATES or not events
            or len(events) != head["version"]
            or len(events) > MAX_EVENTS):
        raise ShadowQueueBlocked("shadow_history_invalid")
    previous = ZERO
    state = ""
    last: dict[str, Any] | None = None
    for version, (event_version, action, op, prev, digest, raw) in enumerate(events, 1):
        try:
            event = json.loads(raw)
        except (TypeError, ValueError):
            raise ShadowQueueBlocked("shadow_history_corrupt") from None
        if (not isinstance(event, dict) or set(event) != EVENT_FIELDS
                or event["schema_version"] != SCHEMA
                or event["version"] != version or event_version != version
                or event["action"] != action or event["operation_id"] != op
                or (event["account_id"], event["slot_id"], event["queue_id"]) != key
                or prev != previous or event["previous_event_sha256"] != prev
                or _hash(event) != digest):
            raise ShadowQueueBlocked("shadow_history_tampered")
        new_state = (
            "SHADOW_BLOCKED" if (
                (action == "IMPORT" and version == 1 and not state)
                or (action in ("REFRESH", "OBSERVE") and state == "SHADOW_BLOCKED")
            )
            else "CONFLICT_BLOCKED" if action == "DRIFT" and state == "SHADOW_BLOCKED"
            else "SOURCE_UNAVAILABLE_BLOCKED"
            if action == "SOURCE_LOST" and state == "SHADOW_BLOCKED"
            else None
        )
        if new_state is None or event["state"] != new_state:
            raise ShadowQueueBlocked("shadow_transition_tampered")
        if last and action in ("OBSERVE", "DRIFT", "SOURCE_LOST") and any(
            event[field] != last[field] for field in FIELDS
        ):
            raise ShadowQueueBlocked("shadow_snapshot_event_tampered")
        if action in ("IMPORT", "REFRESH", "OBSERVE") and (
            event["observed_sha256"] != event["snapshot_sha256"]
        ):
            raise ShadowQueueBlocked("shadow_observation_tampered")
        state, previous, last = new_state, digest, event
    assert last is not None
    for field in ("state", *FIELDS, "last_event_sha256", "updated_at"):
        expected = (previous if field == "last_event_sha256"
                    else last["created_at"] if field == "updated_at"
                    else last[field])
        if head[field] != expected:
            raise ShadowQueueBlocked("shadow_head_tampered")
    try:
        decoded = json.loads(head["snapshot_json"])
        if (not isinstance(decoded, dict) or set(decoded) != {
            "queue", "plan", "receipts",
        } or _hash(decoded) != head["snapshot_sha256"]
                or head["queue_sha256"] != queue_fingerprint(decoded["queue"])
                or decoded["queue"].get("revision") != head["queue_revision"]
                or tuple(decoded["queue"].get(f) for f in (
                    "account_id", "slot_id", "queue_id",
                )) != key):
            raise ShadowQueueBlocked("shadow_snapshot_tampered")
        _safe_payload(decoded)
    except (TypeError, ValueError, KeyError, AttributeError):
        raise ShadowQueueBlocked("shadow_snapshot_tampered") from None


def _write(
    db: sqlite3.Connection, key: tuple[str, str, str],
    *, old: dict[str, Any] | None, fields: dict[str, str],
    snapshot_json: str, observed_sha: str,
    operation_id: str, action: str, actor: str, now: datetime,
) -> dict[str, Any]:
    version = 1 if old is None else old["version"] + 1
    if version > MAX_EVENTS:
        raise ShadowQueueBlocked("shadow_history_at_capacity")
    state = ("CONFLICT_BLOCKED" if action == "DRIFT"
             else "SOURCE_UNAVAILABLE_BLOCKED" if action == "SOURCE_LOST"
             else "SHADOW_BLOCKED")
    event = {
        "schema_version": SCHEMA, "operation_id": operation_id,
        "account_id": key[0], "slot_id": key[1], "queue_id": key[2],
        "version": version, "action": action, "state": state,
        **fields, "observed_sha256": observed_sha, "actor": actor,
        "created_at": now.isoformat(timespec="seconds"),
        "previous_event_sha256": old["last_event_sha256"] if old else ZERO,
    }
    digest = _hash(event)
    if old is None:
        db.execute(
            """INSERT INTO sns_media_shadow_queue_heads(
                account_id,slot_id,queue_id,version,state,
                queue_revision,queue_sha256,context_sha256,snapshot_sha256,
                snapshot_json,last_event_sha256,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (*key, version, state, *(fields[f] for f in FIELDS),
             snapshot_json, digest, event["created_at"]),
        )
    else:
        result = db.execute(
            """UPDATE sns_media_shadow_queue_heads SET
                version=?,state=?,queue_revision=?,queue_sha256=?,
                context_sha256=?,snapshot_sha256=?,snapshot_json=?,
                last_event_sha256=?,updated_at=?
               WHERE account_id=? AND slot_id=? AND queue_id=?
                 AND version=? AND last_event_sha256=?""",
            (version, state, *(fields[f] for f in FIELDS),
             snapshot_json, digest, event["created_at"],
             *key, old["version"], old["last_event_sha256"]),
        )
        if result.rowcount != 1:
            raise ShadowQueueBlocked("shadow_concurrent_change")
    db.execute(
        """INSERT INTO sns_media_shadow_queue_events(
           operation_id,account_id,slot_id,queue_id,version,
           action,previous_event_sha256,event_sha256,payload_json)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (operation_id, *key, version, action,
         event["previous_event_sha256"], digest, _canon(event)),
    )
    return {
        "status": state, "shadow_version": version,
        "shadow_event_sha256": digest,
        "effective_approval": False, "publish_authorized": False,
        "dispatch_allowed": False, "publish_attempted": False,
        "ready_transitions_performed": False,
        "external_queue_atomicity_guaranteed": False,
    }


class _FrozenReader:
    """Precommit must validate the ONE source snapshot already fetched."""
    def __init__(self, context: CanonicalReviewContext, key: tuple[str, str, str]):
        self.context, self.key = context, key

    def load_current(self, account_id: str, slot_id: str,
                     queue_id: str) -> CanonicalReviewContext:
        if (account_id, slot_id, queue_id) != self.key:
            raise ShadowQueueBlocked("shadow_candidate_mismatch")
        return self.context


def _trusted_snapshot(
    db: sqlite3.Connection, key: tuple[str, str, str], *,
    source: CanonicalProtectedReviewReader | None,
    verifier: PinnedRS256SessionVerifier | None,
    bearer: str, issuer: str, now: datetime,
) -> tuple[str, dict[str, str]]:
    if isinstance(getattr(source, "source", None), SQLiteShadowOperationalSnapshot):
        raise ShadowQueueBlocked("shadow_recursive_source_not_allowed")
    ctx = _source(db, source, key)
    try:
        plan_sha = _sha256(ctx.plan)
        choices = _validate_plan(ctx.plan)
        events, receipts_head = _validate_history(ctx.receipts, plan_sha, choices)
        matching = [
            item for item in events
            if (item["account_id"], item["slot_id"], item["queue_id"]) == key
        ]
        if not matching:
            raise ShadowQueueBlocked("shadow_receipt_missing")
        req = ReviewRequest(
            account_id=key[0], slot_id=key[1], queue_id=key[2],
            expected_queue_revision=ctx.queue["revision"],
            expected_plan_sha256=plan_sha,
            expected_receipts_head_sha256=receipts_head,
            draft_event_sha256=matching[-1]["event_sha256"],
            confirm_human_review=True,
            expected_queue_sha256=queue_fingerprint(ctx.queue),
        )
        verification = evaluate_precommit(
            req, bearer, verifier=verifier,
            canonical=_FrozenReader(ctx, key),
            trusted_issuer=issuer, as_of=now,
        )
        if (verification.get("effective_approval") is not False
                or verification.get("publish_authorized") is not False
                or verification.get("session_verified_by_adapter") is not True):
            raise ShadowQueueBlocked("shadow_verification_not_nonauthorizing")
        data, fields = _snapshot(ctx)
        return _canon(data), fields
    except Exception:
        raise ShadowQueueBlocked("shadow_source_not_safe") from None


def _validate_expected(
    head: dict[str, Any] | None, expected_version: int,
    expected_head_sha256: str,
) -> None:
    if (type(expected_version) is not int or expected_version < 0
            or not isinstance(expected_head_sha256, str)):
        raise ShadowQueueBlocked("shadow_expected_version_invalid")
    if head is None:
        if expected_version != 0 or expected_head_sha256 != ZERO:
            raise ShadowQueueBlocked("shadow_expected_version_conflict")
    elif (head["version"] != expected_version
          or head["last_event_sha256"] != expected_head_sha256):
        raise ShadowQueueBlocked("shadow_expected_version_conflict")


def _may_refresh(db: sqlite3.Connection, key: tuple[str, str, str]) -> bool:
    # Any review in history freezes this candidate permanently. A revoked
    # review is still a review; no silent refreshing to shed its identity.
    for table in (
        "sns_media_review_events", "sns_media_review_queue_bindings",
        "sns_media_publish_intent_heads", "sns_media_dispatch_heads",
    ):
        row = db.execute(
            f"""SELECT 1 FROM {table}
                WHERE account_id=? AND slot_id=? AND queue_id=? LIMIT 1""",
            key,
        ).fetchone()
        if row:
            return False
    return True


class SQLiteShadowOperationalSnapshot:
    """Read-only internal source for CanonicalProtectedReviewReader.

    The SAME protected SQLite connection is used by review, intent and dispatch
    under BEGIN IMMEDIATE. No external provider is consulted at load time.
    A 90-second observation lease and independently checked evidence prevent
    indefinite reuse of a stale or revoked local snapshot. This is NOT a
    production freshness guarantee across Sheets and SQLite.
    """

    def __init__(
        self, *, db: sqlite3.Connection, vault: ProtectedEvidenceVault,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if (not isinstance(db, sqlite3.Connection)
                or not isinstance(vault, ProtectedEvidenceVault)
                or vault.connection is not db):
            raise ShadowQueueBlocked("shadow_storage_binding_invalid")
        self.db, self.vault = db, vault
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def load(
        self, account_id: str, slot_id: str, queue_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        key = _key(account_id, slot_id, queue_id)
        try:
            head = _row(self.db, key)
            _history(self.db, key, head)
            if not head or head["state"] != "SHADOW_BLOCKED":
                raise ShadowQueueBlocked("shadow_not_readable")
            now = _utc(self.clock(), "shadow_clock_invalid")
            observed = _time(head["updated_at"], "shadow_clock_invalid")
            if (observed > now + CLOCK_SKEW or now - observed > LEASE):
                raise ShadowQueueBlocked("shadow_observation_expired")
            data = json.loads(head["snapshot_json"])
            plan, receipts, queue = (
                data["plan"], data["receipts"], data["queue"],
            )
            req = ReviewRequest(
                account_id=key[0], slot_id=key[1], queue_id=key[2],
                expected_queue_revision=head["queue_revision"],
                expected_plan_sha256=ZERO,
                expected_receipts_head_sha256=ZERO,
                draft_event_sha256=ZERO, confirm_human_review=True,
                expected_queue_sha256=head["queue_sha256"],
            )
            _verify_queue(queue, req)
            choices = _validate_plan(plan)
            events, _ = _validate_history(receipts, _sha256(plan), choices)
            matching = [
                e for e in events if (
                    e["account_id"], e["slot_id"], e["queue_id"]
                ) == key
            ]
            if not matching:
                raise ShadowQueueBlocked("shadow_receipt_invalid")
            refs = matching[-1]["evidence_ids"]
            evidence = {
                ref: self.vault.get_current(ref) for ref in refs.values()
            }
            _verify_evidence(matching[-1], queue, evidence, now)
            current = CanonicalReviewContext(
                plan=plan, receipts=receipts, queue=queue,
                evidence_by_id=evidence,
            )
            if context_fingerprint(current) != head["context_sha256"]:
                raise ShadowQueueBlocked("shadow_evidence_drift")
            return plan, receipts, queue
        except Exception:
            raise ShadowQueueBlocked("shadow_snapshot_unavailable") from None


class MediaShadowQueueAuthority:
    """Authenticated import and reconciliation; every state is BLOCKED."""

    def __init__(self, db: sqlite3.Connection) -> None:
        if not isinstance(db, sqlite3.Connection):
            raise ShadowQueueBlocked("shadow_database_unavailable")
        self.db = db

    def capture(
        self, *, key: tuple[str, str, str], operation_id: str,
        expected_version: int, expected_head_sha256: str,
        verifier: PinnedRS256SessionVerifier | None, bearer: str,
        trusted_issuer: str, source: CanonicalProtectedReviewReader | None,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Import/refresh a trusted server snapshot before any review exists."""
        _database(self.db)
        key = _key(*key)
        if not isinstance(operation_id, str) or not OP_RE.fullmatch(operation_id):
            raise ShadowQueueBlocked("shadow_operation_invalid")
        now = _utc(as_of or datetime.now(timezone.utc), "shadow_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            actor = _actor(
                self.db, verifier=verifier, bearer=bearer,
                issuer=trusted_issuer, key=key, now=now,
            )
            head = _row(self.db, key)
            _history(self.db, key, head)
            _validate_expected(head, expected_version, expected_head_sha256)
            if (head is not None and head["state"] != "SHADOW_BLOCKED") or not _may_refresh(
                self.db, key,
            ):
                raise ShadowQueueBlocked("shadow_review_frozen")
            payload, fields = _trusted_snapshot(
                self.db, key, source=source, verifier=verifier, bearer=bearer,
                issuer=trusted_issuer, now=now,
            )
            result = _write(
                self.db, key, old=head, fields=fields,
                snapshot_json=payload, observed_sha=fields["snapshot_sha256"],
                operation_id=operation_id,
                action="REFRESH" if head else "IMPORT", actor=actor, now=now,
            )
            self.db.commit()
            return result
        except ShadowQueueBlocked:
            self.db.rollback()
            raise
        except sqlite3.IntegrityError:
            self.db.rollback()
            raise ShadowQueueBlocked("shadow_duplicate_or_replay") from None
        except Exception:
            self.db.rollback()
            raise ShadowQueueBlocked("shadow_capture_failed") from None

    def observe(
        self, *, key: tuple[str, str, str], operation_id: str,
        expected_version: int, expected_head_sha256: str,
        verifier: PinnedRS256SessionVerifier | None, bearer: str,
        trusted_issuer: str, source: CanonicalProtectedReviewReader | None,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Reconcile with an independently fetched operational snapshot.

        An observation that differs, is unsafe or cannot be read permanently
        quarantines the shadow. It never changes the saved caption or permits
        a post. Exact match renews the bounded read lease.
        """
        _database(self.db)
        key = _key(*key)
        if not isinstance(operation_id, str) or not OP_RE.fullmatch(operation_id):
            raise ShadowQueueBlocked("shadow_operation_invalid")
        now = _utc(as_of or datetime.now(timezone.utc), "shadow_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            actor = _actor(
                self.db, verifier=verifier, bearer=bearer,
                issuer=trusted_issuer, key=key, now=now,
            )
            head = _row(self.db, key)
            _history(self.db, key, head)
            _validate_expected(head, expected_version, expected_head_sha256)
            if not head or head["state"] != "SHADOW_BLOCKED":
                raise ShadowQueueBlocked("shadow_not_observable")
            action = "OBSERVE"
            observed_hash = head["snapshot_sha256"]
            try:
                snapshot, fresh = _trusted_snapshot(
                    self.db, key, source=source, verifier=verifier, bearer=bearer,
                    issuer=trusted_issuer, now=now,
                )
                observed_hash = fresh["snapshot_sha256"]
                if (observed_hash != head["snapshot_sha256"]
                        or any(fresh[f] != head[f] for f in FIELDS)
                        or snapshot != head["snapshot_json"]):
                    action = "DRIFT"
            except Exception:
                action = "SOURCE_LOST"
                observed_hash = ZERO
            result = _write(
                self.db, key, old=head,
                fields={field: head[field] for field in FIELDS},
                snapshot_json=head["snapshot_json"],
                observed_sha=observed_hash, operation_id=operation_id,
                action=action, actor=actor, now=now,
            )
            self.db.commit()
            return result
        except ShadowQueueBlocked:
            self.db.rollback()
            raise
        except sqlite3.IntegrityError:
            self.db.rollback()
            raise ShadowQueueBlocked("shadow_duplicate_or_replay") from None
        except Exception:
            self.db.rollback()
            raise ShadowQueueBlocked("shadow_observation_failed") from None

    def inspect(self, *, key: tuple[str, str, str]) -> dict[str, Any]:
        """Return hashes/versions only; never original content or user tokens."""
        _database(self.db)
        key = _key(*key)
        try:
            head = _row(self.db, key)
            _history(self.db, key, head)
            return {
                "status": head["state"] if head else "NO_SNAPSHOT",
                "shadow_version": head["version"] if head else 0,
                "shadow_event_sha256": head["last_event_sha256"] if head else ZERO,
                "queue_sha256": head["queue_sha256"] if head else ZERO,
                "effective_approval": False, "publish_authorized": False,
                "dispatch_allowed": False, "external_queue_atomicity_guaranteed": False,
            }
        except sqlite3.Error:
            raise ShadowQueueBlocked("shadow_inspection_failed") from None
