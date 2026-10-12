#!/usr/bin/env python3
"""5B-6I: independently signed mirror service & isolated OFFLINE readback trial.

Do not confuse local in-memory rehearsal with a Sheets integration: no Google
credentials, HTTP client, endpoint, production migration or live delivery ACK
exists here. Only an exact in-memory adapter can be used; reviewers cannot
authenticate as services, and all status returns remain publishing BLOCKED.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from media_mirror_outbox import (
    SHA, ZERO, _audit as _outbox_audit, _head as _outbox_head,
    _projection_for as _verified_preview,
)
from media_publish_intent_authority import _database
from media_review_trusted_precommit import _time, _utc
from media_review_verified_identity import (
    SAFE_NAME, _epoch, _json_object, _unbase,
)

MIGRATION = Path(__file__).resolve().parents[1] / "db" / "migrations" / (
    "0009_sns_media_mirror_rehearsal.sql"
)
SERVICE_AUDIENCE = "sns-growth-mirror-rehearsal"
SERVICE_USE = "mirror_rehearsal_only"
SERVICE_SCOPE = "mirror:rehearse"
OP = re.compile(r"rehearsal_[A-Za-z0-9_.:-]{12,105}\Z")
SHEET_ID = re.compile(r"[A-Za-z0-9_-]{8,160}\Z")
TAB = re.compile(r"mirror_preview_[A-Za-z0-9_]{2,80}\Z")
SCHEMA = "sns_mirror_rehearsal_audit_v1"
HEAD_FIELDS = (
    "account_id", "version", "state", "projection_sha256",
    "last_event_sha256", "updated_at",
)
EVENT_FIELDS = frozenset((
    "schema_version", "operation_id", "event_sha256", "destination_id",
    "account_id", "version", "state", "action", "projection_sha256",
    "actor", "reason", "created_at", "previous_event_sha256",
))
MAX_EVENTS = 8
STATES = {
    "PREPARE": "PREPARED_BLOCKED",
    "SIMULATED_READBACK": "SIMULATED_READBACK_BLOCKED",
    "OUTCOME_UNKNOWN": "OUTCOME_UNKNOWN_BLOCKED",
    "READ_ONLY_RECONCILE": "SIMULATED_RECONCILED_BLOCKED",
    "CONFLICT": "CONFLICT_BLOCKED",
}


class MirrorRehearsalBlocked(ValueError):
    """Sanitized reason code only, never JWT, provider body or sheet contents."""


def initialize_mirror_rehearsal_schema(db: sqlite3.Connection) -> None:
    """Explicit OFFLINE migration 0009; no auto-provisioning at request time."""
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise MirrorRehearsalBlocked("rehearsal_migration_requires_autocommit")
    try:
        for table in (
            "sns_media_mirror_outbox_heads", "sns_media_sheet_mirror_previews",
        ):
            if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone():
                raise MirrorRehearsalBlocked("rehearsal_parent_schema_missing")
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
        db.execute("PRAGMA foreign_keys=ON")
    except (sqlite3.Error, OSError):
        raise MirrorRehearsalBlocked("rehearsal_migration_failed") from None


def _canon(value: dict[str, Any]) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        allow_nan=False, ensure_ascii=True,
    )


def _hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canon(value).encode("ascii")).hexdigest()


class PinnedMirrorServiceVerifier:
    """Read-only service JWT validator with separate audience and DB grants.

    Public keys and issuer MUST be pinned by the trusted server, not supplied
    by a caller. Service subjects cannot obtain media review privileges.
    """

    def __init__(
        self, *, db: sqlite3.Connection, issuer: str,
        public_keys_by_kid: Mapping[str, bytes],
    ) -> None:
        if (not isinstance(db, sqlite3.Connection) or not isinstance(issuer, str)
                or not issuer.startswith("https://")
                or not public_keys_by_kid):
            raise MirrorRehearsalBlocked("rehearsal_service_config_invalid")
        keys: dict[str, rsa.RSAPublicKey] = {}
        try:
            for kid, pem in public_keys_by_kid.items():
                if not isinstance(kid, str) or SAFE_NAME.fullmatch(kid) is None:
                    raise MirrorRehearsalBlocked("rehearsal_key_invalid")
                key = serialization.load_pem_public_key(pem)
                if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 2048:
                    raise MirrorRehearsalBlocked("rehearsal_key_invalid")
                keys[kid] = key
        except (ValueError, TypeError):
            raise MirrorRehearsalBlocked("rehearsal_key_invalid") from None
        self.db, self.issuer, self.keys = db, issuer, keys

    def verify(
        self, token: str, *, destination_id: str,
        account_id: str, now: datetime,
    ) -> str:
        current = _utc(now, "rehearsal_clock_invalid")
        if not isinstance(token, str) or not 16 <= len(token) <= 4096:
            raise MirrorRehearsalBlocked("rehearsal_service_token_invalid")
        parts = token.split(".")
        if len(parts) != 3:
            raise MirrorRehearsalBlocked("rehearsal_service_token_invalid")
        header_part, claims_part, sig_part = parts
        try:
            header = _json_object(_unbase(header_part))
            claims = _json_object(_unbase(claims_part))
            signature = _unbase(sig_part)
        except Exception:
            raise MirrorRehearsalBlocked("rehearsal_service_token_invalid") from None
        kid = header.get("kid")
        if (header.get("typ") != "JWT" or header.get("alg") != "RS256"
                or not isinstance(kid, str) or kid not in self.keys):
            raise MirrorRehearsalBlocked("rehearsal_service_signature_invalid")
        try:
            self.keys[kid].verify(
                signature, (header_part + "." + claims_part).encode("ascii"),
                padding.PKCS1v15(), hashes.SHA256(),
            )
        except (InvalidSignature, ValueError):
            raise MirrorRehearsalBlocked("rehearsal_service_signature_invalid") from None
        if (claims.get("iss") != self.issuer
                or claims.get("aud") != SERVICE_AUDIENCE
                or claims.get("token_use") != SERVICE_USE
                or claims.get("scope") != SERVICE_SCOPE):
            raise MirrorRehearsalBlocked("rehearsal_service_claims_invalid")
        sub, sid, jti = (claims.get("sub"), claims.get("sid"), claims.get("jti"))
        if any(
            not isinstance(x, str) or SAFE_NAME.fullmatch(x) is None
            for x in (sub, sid, jti)
        ):
            raise MirrorRehearsalBlocked("rehearsal_service_identity_invalid")
        try:
            iat, nbf, exp = (
                _epoch(claims, "iat"), _epoch(claims, "nbf"),
                _epoch(claims, "exp"),
            )
        except Exception:
            raise MirrorRehearsalBlocked("rehearsal_service_time_invalid") from None
        time = current.timestamp()
        if (iat > time + 30 or nbf > time + 30 or exp <= time
                or exp <= iat or exp - iat > 300):
            raise MirrorRehearsalBlocked("rehearsal_service_time_invalid")
        fingerprint = hashlib.sha256(token.encode("ascii")).hexdigest()
        try:
            session = self.db.execute(
                """SELECT subject,issuer,token_sha256,token_jti,
                          issued_at,expires_at,revoked_at,enabled
                   FROM sns_mirror_rehearsal_service_sessions
                   WHERE session_id=?""",
                (sid,),
            ).fetchone()
            policy = self.db.execute(
                """SELECT account_id,service_subject,reporting_spreadsheet_id,
                          operational_spreadsheet_id,reporting_tab,mode,enabled
                   FROM sns_mirror_rehearsal_destinations
                   WHERE destination_id=?""", (destination_id,),
            ).fetchone()
        except sqlite3.Error:
            raise MirrorRehearsalBlocked("rehearsal_service_store_unavailable") from None
        if (session is None or session != (
                sub, self.issuer, fingerprint, jti, iat, exp, None, 1,
        )):
            raise MirrorRehearsalBlocked("rehearsal_service_session_not_active")
        if (policy is None or policy[0] != account_id or policy[1] != sub
                or policy[5:] != ("ISOLATED_REPORTING_ONLY", 1)
                or policy[2] == policy[3]
                or not isinstance(policy[2], str)
                or not SHEET_ID.fullmatch(policy[2])
                or not isinstance(policy[3], str)
                or not SHEET_ID.fullmatch(policy[3])
                or not isinstance(policy[4], str)
                or not TAB.fullmatch(policy[4])):
            raise MirrorRehearsalBlocked("rehearsal_destination_not_permitted")
        return sub


class InMemoryReportingReplica:
    """Exact, dependency-free fake; cannot make an HTTP/Sheets request."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, str, str], dict[str, Any]] = {}
        self.write_calls = 0
        self.fail_before_write = False
        self.fail_after_write = False
        self.fail_read = False

    @staticmethod
    def key(dest: str, projection: dict[str, Any]) -> tuple[str, str, str, str]:
        return (
            dest, projection["account_id"],
            projection["slot_id"], projection["queue_id"],
        )

    def read(self, dest: str, projection: dict[str, Any]) -> dict[str, Any] | None:
        if self.fail_read:
            raise OSError("offline replica read interrupted")
        value = self.rows.get(self.key(dest, projection))
        return copy.deepcopy(value)

    def compare_and_swap(
        self, dest: str, projection: dict[str, Any],
        prior: dict[str, Any] | None,
    ) -> None:
        if self.fail_before_write:
            raise OSError("offline replica write interrupted")
        key = self.key(dest, projection)
        if self.rows.get(key) != prior:
            raise MirrorRehearsalBlocked("rehearsal_replica_cas_conflict")
        self.write_calls += 1
        self.rows[key] = copy.deepcopy(projection)
        if self.fail_after_write:
            raise OSError("offline replica outcome unknown")


def _head(
    db: sqlite3.Connection, event_sha256: str, destination_id: str,
) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT " + ",".join(HEAD_FIELDS) + """
         FROM sns_mirror_rehearsal_heads
         WHERE event_sha256=? AND destination_id=?""",
        (event_sha256, destination_id),
    ).fetchone()
    return dict(zip(HEAD_FIELDS, row)) if row else None


def _audit(
    db: sqlite3.Connection, event_sha256: str, destination_id: str,
    head: dict[str, Any] | None,
) -> None:
    rows = db.execute(
        """SELECT version,action,operation_id,previous_event_sha256,
                  audit_sha256,payload_json
           FROM sns_mirror_rehearsal_events
           WHERE event_sha256=? AND destination_id=? ORDER BY version""",
        (event_sha256, destination_id),
    ).fetchall()
    if head is None:
        if rows:
            raise MirrorRehearsalBlocked("rehearsal_orphan_events")
        return
    if not rows or len(rows) != head["version"] or len(rows) > MAX_EVENTS:
        raise MirrorRehearsalBlocked("rehearsal_history_invalid")
    last = None
    state = ""
    previous = ZERO
    for index, (number, action, operation, prev, digest, raw) in enumerate(rows, 1):
        try:
            event = json.loads(raw)
        except (TypeError, ValueError):
            raise MirrorRehearsalBlocked("rehearsal_history_corrupt") from None
        if (not isinstance(event, dict) or set(event) != EVENT_FIELDS
                or event["schema_version"] != SCHEMA
                or number != index or event["version"] != index
                or event["action"] != action or event["operation_id"] != operation
                or event["event_sha256"] != event_sha256
                or event["destination_id"] != destination_id
                or event["previous_event_sha256"] != previous
                or prev != previous or digest != _hash(event)):
            raise MirrorRehearsalBlocked("rehearsal_history_tampered")
        next_state = (
            "PREPARED_BLOCKED" if index == 1 and action == "PREPARE"
            else "SIMULATED_READBACK_BLOCKED"
            if state == "PREPARED_BLOCKED" and action == "SIMULATED_READBACK"
            else "OUTCOME_UNKNOWN_BLOCKED"
            if state == "PREPARED_BLOCKED" and action == "OUTCOME_UNKNOWN"
            else "SIMULATED_RECONCILED_BLOCKED"
            if state in ("PREPARED_BLOCKED", "OUTCOME_UNKNOWN_BLOCKED")
            and action == "READ_ONLY_RECONCILE"
            else "CONFLICT_BLOCKED"
            if state in ("PREPARED_BLOCKED", "OUTCOME_UNKNOWN_BLOCKED")
            and action == "CONFLICT"
            else None
        )
        if next_state is None or event["state"] != next_state:
            raise MirrorRehearsalBlocked("rehearsal_lifecycle_tampered")
        if last is not None and (
            event["account_id"] != last["account_id"]
            or event["projection_sha256"] != last["projection_sha256"]
        ):
            raise MirrorRehearsalBlocked("rehearsal_identity_tampered")
        last, state, previous = event, next_state, digest
    assert last is not None
    for field in HEAD_FIELDS:
        expected = (previous if field == "last_event_sha256"
                    else last["created_at"] if field == "updated_at"
                    else last[field])
        if head[field] != expected:
            raise MirrorRehearsalBlocked("rehearsal_head_tampered")


def _write(
    db: sqlite3.Connection, *, event_sha256: str, destination_id: str,
    account_id: str, projection_sha256: str, old: dict[str, Any] | None,
    operation_id: str, action: str, actor: str,
    reason: str, now: datetime,
) -> dict[str, Any]:
    if not isinstance(operation_id, str) or OP.fullmatch(operation_id) is None:
        raise MirrorRehearsalBlocked("rehearsal_operation_invalid")
    version = 1 if old is None else old["version"] + 1
    if version > MAX_EVENTS:
        raise MirrorRehearsalBlocked("rehearsal_history_capacity")
    state = STATES[action]
    payload = {
        "schema_version": SCHEMA, "operation_id": operation_id,
        "event_sha256": event_sha256, "destination_id": destination_id,
        "account_id": account_id, "version": version, "state": state,
        "action": action, "projection_sha256": projection_sha256,
        "actor": actor, "reason": reason,
        "created_at": now.isoformat(timespec="seconds"),
        "previous_event_sha256": old["last_event_sha256"] if old else ZERO,
    }
    digest = _hash(payload)
    if old is None:
        db.execute(
            """INSERT INTO sns_mirror_rehearsal_heads (
               event_sha256,destination_id,account_id,version,state,
               projection_sha256,last_event_sha256,updated_at
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (event_sha256, destination_id, account_id, version,
             state, projection_sha256, digest, payload["created_at"]),
        )
    else:
        changed = db.execute(
            """UPDATE sns_mirror_rehearsal_heads SET
                 version=?,state=?,last_event_sha256=?,updated_at=?
               WHERE event_sha256=? AND destination_id=?
                 AND version=? AND last_event_sha256=?""",
            (version, state, digest, payload["created_at"],
             event_sha256, destination_id,
             old["version"], old["last_event_sha256"]),
        )
        if changed.rowcount != 1:
            raise MirrorRehearsalBlocked("rehearsal_cas_conflict")
    db.execute(
        """INSERT INTO sns_mirror_rehearsal_events(
           operation_id,event_sha256,destination_id,version,action,
           previous_event_sha256,audit_sha256,payload_json
           ) VALUES(?,?,?,?,?,?,?,?)""",
        (operation_id, event_sha256, destination_id, version, action,
         payload["previous_event_sha256"], digest, _canon(payload)),
    )
    return {
        "status": state, "rehearsal_version": version,
        "audit_sha256": digest,
        "simulated_readback_verified": action in (
            "SIMULATED_READBACK", "READ_ONLY_RECONCILE",
        ),
        "real_sheets_write_performed": False,
        "external_delivery_confirmed": False,
        "publish_authorized": False, "dispatch_allowed": False,
        "sheets_write_allowed": False,
    }


class MirrorServiceRehearsal:
    """Offline double-commit protocol. No legitimate live transport type fits."""

    def __init__(
        self, *, db: sqlite3.Connection,
        verifier: PinnedMirrorServiceVerifier,
        replica: InMemoryReportingReplica,
    ) -> None:
        if (not isinstance(db, sqlite3.Connection)
                or type(verifier) is not PinnedMirrorServiceVerifier
                or verifier.db is not db
                or type(replica) is not InMemoryReportingReplica):
            raise MirrorRehearsalBlocked("rehearsal_offline_adapter_only")
        self.db, self.verifier, self.replica = db, verifier, replica

    def _authorized(
        self, *, event_sha256: str, destination_id: str,
        token: str, now: datetime, require_live_lease: bool = True,
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        if (not isinstance(event_sha256, str) or SHA.fullmatch(event_sha256) is None
                or not isinstance(destination_id, str)
                or SAFE_NAME.fullmatch(destination_id) is None):
            raise MirrorRehearsalBlocked("rehearsal_identifier_invalid")
        outbox = _outbox_head(self.db, event_sha256)
        _outbox_audit(self.db, event_sha256, outbox)
        if not outbox or outbox["state"] != "CLAIMED_BLOCKED":
            raise MirrorRehearsalBlocked("rehearsal_outbox_not_claimed")
        # A new write requires the short reviewer claim lease. Read-only
        # crash reconciliation may run later, but still requires an active
        # signed service session, current writer and immutable outbox state.
        if require_live_lease and _time(
            outbox["lease_expires_at"], "rehearsal_claim_expired",
        ) <= now:
            raise MirrorRehearsalBlocked("rehearsal_claim_expired")
        actor = self.verifier.verify(
            token, destination_id=destination_id,
            account_id=outbox["account_id"], now=now,
        )
        preview = _verified_preview(self.db, event_sha256, outbox)
        return actor, outbox, preview

    def run_once(
        self, *, event_sha256: str, destination_id: str,
        token: str, operation_id: str,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Records PREPARE first, then only a synthetic memory CAS/readback.

        A crash after PREPARE must NOT auto-retry; readback_only may later
        reconcile after a separately authenticated read, never a second write.
        """
        _database(self.db)
        if (not isinstance(operation_id, str)
                or OP.fullmatch(operation_id) is None
                or len(operation_id) > 95):
            raise MirrorRehearsalBlocked("rehearsal_operation_invalid")
        now = _utc(as_of or datetime.now(timezone.utc), "rehearsal_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            actor, outbox, preview = self._authorized(
                event_sha256=event_sha256, destination_id=destination_id,
                token=token, now=now,
            )
            existing = _head(self.db, event_sha256, destination_id)
            _audit(self.db, event_sha256, destination_id, existing)
            if existing:
                raise MirrorRehearsalBlocked("rehearsal_already_prepared")
            encoded = _hash(preview)
            prepared = _write(
                self.db, event_sha256=event_sha256, destination_id=destination_id,
                account_id=outbox["account_id"], projection_sha256=encoded,
                old=None, operation_id=operation_id, action="PREPARE",
                actor=actor, reason="offline_rehearsal_only", now=now,
            )
            self.db.commit()
        except MirrorRehearsalBlocked:
            self.db.rollback()
            raise
        except sqlite3.IntegrityError:
            self.db.rollback()
            raise MirrorRehearsalBlocked("rehearsal_duplicate_or_replay") from None
        except Exception:
            self.db.rollback()
            raise MirrorRehearsalBlocked("rehearsal_prepare_failed") from None

        action, reason = "SIMULATED_READBACK", "memory_readback_matches"
        try:
            prior = self.replica.read(destination_id, preview)
            if prior is not None and prior != preview:
                if (not isinstance(prior, dict)
                        or prior.get("account_id") != preview["account_id"]
                        or prior.get("writer_version", 0) >= preview["writer_version"]):
                    action, reason = "CONFLICT", "replica_existing_conflict"
                else:
                    self.replica.compare_and_swap(destination_id, preview, prior)
            elif prior is None:
                self.replica.compare_and_swap(destination_id, preview, None)
            if action != "CONFLICT":
                verify = self.replica.read(destination_id, preview)
                if verify != preview:
                    action, reason = "OUTCOME_UNKNOWN", "memory_readback_unverified"
        except Exception:
            action, reason = "OUTCOME_UNKNOWN", "memory_response_unknown"

        try:
            self.db.execute("BEGIN IMMEDIATE")
            head = _head(self.db, event_sha256, destination_id)
            _audit(self.db, event_sha256, destination_id, head)
            if (head is None or head["state"] != "PREPARED_BLOCKED"
                    or head["last_event_sha256"] != prepared["audit_sha256"]):
                raise MirrorRehearsalBlocked("rehearsal_finalize_conflict")
            result = _write(
                self.db, event_sha256=event_sha256, destination_id=destination_id,
                account_id=head["account_id"],
                projection_sha256=head["projection_sha256"],
                old=head, operation_id=operation_id + "_result",
                action=action, actor=actor, reason=reason, now=now,
            )
            self.db.commit()
            return result
        except MirrorRehearsalBlocked:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            # PREPARED persists from before the synthetic write: never replay.
            raise MirrorRehearsalBlocked("rehearsal_finalize_unverified") from None

    def readback_only(
        self, *, event_sha256: str, destination_id: str,
        token: str, operation_id: str,
        expected_version: int, expected_audit_sha256: str,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """Explicit operator-authorized READ ONLY reconciliation of unknowns."""
        _database(self.db)
        if (not isinstance(operation_id, str) or OP.fullmatch(operation_id) is None
                or type(expected_version) is not int
                or not isinstance(expected_audit_sha256, str)):
            raise MirrorRehearsalBlocked("rehearsal_reconcile_arguments_invalid")
        now = _utc(as_of or datetime.now(timezone.utc), "rehearsal_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            actor, outbox, preview = self._authorized(
                event_sha256=event_sha256, destination_id=destination_id,
                token=token, now=now, require_live_lease=False,
            )
            head = _head(self.db, event_sha256, destination_id)
            _audit(self.db, event_sha256, destination_id, head)
            if (head is None or head["state"] not in (
                    "PREPARED_BLOCKED", "OUTCOME_UNKNOWN_BLOCKED",
                ) or head["version"] != expected_version
                    or head["last_event_sha256"] != expected_audit_sha256
                    or head["projection_sha256"] != _hash(preview)):
                raise MirrorRehearsalBlocked("rehearsal_reconcile_conflict")
            try:
                observation = self.replica.read(destination_id, preview)
            except Exception:
                raise MirrorRehearsalBlocked("rehearsal_readback_unavailable") from None
            if observation is None:
                raise MirrorRehearsalBlocked("rehearsal_readback_not_found")
            action = (
                "READ_ONLY_RECONCILE" if observation == preview else "CONFLICT"
            )
            result = _write(
                self.db, event_sha256=event_sha256, destination_id=destination_id,
                account_id=outbox["account_id"],
                projection_sha256=head["projection_sha256"], old=head,
                operation_id=operation_id, action=action, actor=actor,
                reason="read_only_memory_comparison", now=now,
            )
            self.db.commit()
            return result
        except MirrorRehearsalBlocked:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise MirrorRehearsalBlocked("rehearsal_reconcile_failed") from None

    def inspect(self, *, event_sha256: str, destination_id: str) -> dict[str, Any]:
        _database(self.db)
        if (not isinstance(event_sha256, str) or SHA.fullmatch(event_sha256) is None
                or not isinstance(destination_id, str)
                or SAFE_NAME.fullmatch(destination_id) is None):
            raise MirrorRehearsalBlocked("rehearsal_identifier_invalid")
        try:
            head = _head(self.db, event_sha256, destination_id)
            _audit(self.db, event_sha256, destination_id, head)
            return {
                "status": head["state"] if head else "NO_REHEARSAL",
                "version": head["version"] if head else 0,
                "audit_sha256": head["last_event_sha256"] if head else ZERO,
                "external_delivery_confirmed": False,
                "publish_authorized": False, "sheets_write_allowed": False,
            }
        except sqlite3.Error:
            raise MirrorRehearsalBlocked("rehearsal_inspection_failed") from None
