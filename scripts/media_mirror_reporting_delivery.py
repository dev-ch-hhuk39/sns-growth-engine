#!/usr/bin/env python3
"""6J isolated reporting-Sheet delivery protocol, opt-in and NOT deployed.

One protected SQLite PREPARE precedes one bounded values.update in a pinned
reporting-only row. A missing/ambiguous response never retries automatically.
Sheets does not support SQLite cross-store CAS or prove exclusive ACLs; this
cannot authorize any SNS post and must be separately security-reviewed and
canaried prior to enabling a real service identity/network gateway.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from typing import Any

from media_mirror_delivery_identity import (
    MirrorDeliveryBlocked, PinnedLiveMirrorServiceVerifier,
)
from media_mirror_canary_approval import (
    CanaryApprovalBlocked, PinnedTwoOperatorCanaryVerifier,
)
from media_mirror_outbox import (
    SHA, ZERO, _audit as _outbox_audit, _head as _outbox_head,
    _projection_for as _verified_preview,
)
from media_mirror_sheets_adapter import (
    GspreadReportingFixedRow,
)
from media_mirror_readonly_acl_preflight import (
    ReadOnlyGoogleMirrorMetadata, read_only_acl_preflight,
)
from media_publish_intent_authority import _database
from media_review_trusted_precommit import _time, _utc

OP = re.compile(r"delivery_[A-Za-z0-9_.:-]{12,100}\Z")
SCHEMA = "sns_mirror_reporting_delivery_event_v1"
EVENT_FIELDS = frozenset((
    "schema_version","operation_id","event_sha256","destination_id",
    "account_id","row_number","version","action","state",
    "projection_sha256","actor","reason","created_at",
    "previous_event_sha256",
))
HEAD_FIELDS = (
    "account_id","row_number","version","state",
    "projection_sha256","last_event_sha256","updated_at",
)
STATES = {
    "PREPARE":"PREPARED_BLOCKED",
    "READBACK_VERIFIED":"READBACK_VERIFIED_BLOCKED",
    "OUTCOME_UNKNOWN":"OUTCOME_UNKNOWN_BLOCKED",
    "RECONCILE":"RECONCILED_BLOCKED",
    "CONFLICT":"CONFLICT_BLOCKED",
}
MAX_HISTORY = 4


def _canon(obj: dict[str, Any]) -> str:
    return json.dumps(
        obj,sort_keys=True,separators=(",",":"),
        ensure_ascii=True,allow_nan=False,
    )


def _hash(obj: dict[str, Any]) -> str:
    return hashlib.sha256(_canon(obj).encode("ascii")).hexdigest()


def _head(db: sqlite3.Connection, event_id: str, dest: str) -> dict[str, Any] | None:
    row = db.execute(
        "SELECT " + ",".join(HEAD_FIELDS) + """
         FROM sns_mirror_delivery_heads
         WHERE event_sha256=? AND destination_id=?""",
        (event_id,dest),
    ).fetchone()
    return dict(zip(HEAD_FIELDS,row)) if row else None


def _audit(
    db: sqlite3.Connection,event_id: str,dest: str,
    head: dict[str, Any] | None,
) -> None:
    rows = db.execute(
        """SELECT version,action,operation_id,previous_event_sha256,
                  audit_sha256,payload_json
           FROM sns_mirror_delivery_events
           WHERE event_sha256=? AND destination_id=? ORDER BY version""",
        (event_id,dest),
    ).fetchall()
    if head is None:
        if rows:
            raise MirrorDeliveryBlocked("mirror_delivery_orphan_events")
        return
    if (not rows or len(rows) != head["version"]
            or len(rows) > MAX_HISTORY):
        raise MirrorDeliveryBlocked("mirror_delivery_history_invalid")
    previous = ZERO
    last = None
    state = ""
    for index,(ver,action,op,prev,digest,raw) in enumerate(rows,1):
        try:
            event = json.loads(raw)
        except (ValueError,TypeError):
            raise MirrorDeliveryBlocked("mirror_delivery_event_corrupt") from None
        if (not isinstance(event,dict)
                or set(event) != EVENT_FIELDS
                or event["schema_version"] != SCHEMA
                or event["version"] != index or ver != index
                or event["operation_id"] != op or event["action"] != action
                or event["event_sha256"] != event_id
                or event["destination_id"] != dest
                or event["previous_event_sha256"] != previous
                or prev != previous or _hash(event) != digest):
            raise MirrorDeliveryBlocked("mirror_delivery_event_tampered")
        expected = (
            "PREPARED_BLOCKED" if index == 1 and action == "PREPARE"
            else "READBACK_VERIFIED_BLOCKED"
            if state == "PREPARED_BLOCKED" and action == "READBACK_VERIFIED"
            else "OUTCOME_UNKNOWN_BLOCKED"
            if state == "PREPARED_BLOCKED" and action == "OUTCOME_UNKNOWN"
            else "RECONCILED_BLOCKED"
            if state in ("PREPARED_BLOCKED","OUTCOME_UNKNOWN_BLOCKED")
            and action == "RECONCILE"
            else "CONFLICT_BLOCKED"
            if state in ("PREPARED_BLOCKED","OUTCOME_UNKNOWN_BLOCKED")
            and action == "CONFLICT"
            else None
        )
        if expected is None or event["state"] != expected:
            raise MirrorDeliveryBlocked("mirror_delivery_transition_tampered")
        if last and any(
            event[f] != last[f] for f in (
                "account_id","row_number","projection_sha256",
            )
        ):
            raise MirrorDeliveryBlocked("mirror_delivery_identity_tampered")
        state,last,previous = expected,event,digest
    assert last is not None
    for key in HEAD_FIELDS:
        value = (previous if key == "last_event_sha256"
                 else last["created_at"] if key == "updated_at"
                 else last[key])
        if head[key] != value:
            raise MirrorDeliveryBlocked("mirror_delivery_head_tampered")


def _record(
    db: sqlite3.Connection,*, event_id: str,dest: str,account: str,row: int,
    projection_sha: str,old: dict[str, Any] | None,
    operation: str,action: str,actor: str,now: datetime,reason: str,
) -> dict[str, Any]:
    if not isinstance(operation,str) or OP.fullmatch(operation) is None:
        raise MirrorDeliveryBlocked("mirror_delivery_operation_invalid")
    version = 1 if old is None else old["version"]+1
    if version > MAX_HISTORY:
        raise MirrorDeliveryBlocked("mirror_delivery_history_capacity")
    state = STATES[action]
    payload = {
        "schema_version":SCHEMA,"operation_id":operation,
        "event_sha256":event_id,"destination_id":dest,
        "account_id":account,"row_number":row,
        "version":version,"action":action,"state":state,
        "projection_sha256":projection_sha,"actor":actor,
        "reason":reason,"created_at":now.isoformat(timespec="seconds"),
        "previous_event_sha256":old["last_event_sha256"] if old else ZERO,
    }
    digest = _hash(payload)
    if old is None:
        db.execute(
            """INSERT INTO sns_mirror_delivery_heads(
                event_sha256,destination_id,account_id,row_number,version,
                state,projection_sha256,last_event_sha256,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (event_id,dest,account,row,version,state,
             projection_sha,digest,payload["created_at"]),
        )
    else:
        changed = db.execute(
            """UPDATE sns_mirror_delivery_heads SET
                version=?,state=?,last_event_sha256=?,updated_at=?
               WHERE event_sha256=? AND destination_id=?
                AND version=? AND last_event_sha256=?""",
            (version,state,digest,payload["created_at"],event_id,dest,
             old["version"],old["last_event_sha256"]),
        )
        if changed.rowcount != 1:
            raise MirrorDeliveryBlocked("mirror_delivery_version_conflict")
    db.execute(
        """INSERT INTO sns_mirror_delivery_events (
          operation_id,event_sha256,destination_id,version,action,
          previous_event_sha256,audit_sha256,payload_json)
          VALUES(?,?,?,?,?,?,?,?)""",
        (operation,event_id,dest,version,action,
         payload["previous_event_sha256"],digest,_canon(payload)),
    )
    return {
        "status":state,"delivery_version":version,"audit_sha256":digest,
        "publish_authorized":False,"dispatch_allowed":False,
        "operational_queue_modified":False,
    }


class IsolatedSheetsMirrorDelivery:
    """No CLI, route, scheduler or config bootstrap. Default DISABLED."""

    def __init__(
        self,*,db: sqlite3.Connection,
        verifier: PinnedLiveMirrorServiceVerifier,
        adapter: GspreadReportingFixedRow,
        allow_reporting_write: bool = False,
        acl_metadata: ReadOnlyGoogleMirrorMetadata | None = None,
        expected_principal_email: str | None = None,
        canary_approver: PinnedTwoOperatorCanaryVerifier | None = None,
    ) -> None:
        if (not isinstance(db,sqlite3.Connection)
                or type(verifier) is not PinnedLiveMirrorServiceVerifier
                or verifier.db is not db
                or type(adapter) is not GspreadReportingFixedRow
                or type(allow_reporting_write) is not bool):
            raise MirrorDeliveryBlocked("mirror_delivery_configuration_invalid")
        # The old 6J writer could be enabled without checking actual Google
        # Drive ACLs. From 6M onward even explicitly enabled writes must be
        # bound to the *same credential object* used for the readonly ACL
        # probe and the gspread worksheet factory. No bypass for test clients.
        if allow_reporting_write and (
                type(acl_metadata) is not ReadOnlyGoogleMirrorMetadata
                or adapter.factory_credential_bound is not True
                or adapter.auth_credentials is not acl_metadata.credentials
                or not isinstance(expected_principal_email, str)
                or expected_principal_email != acl_metadata.principal_email):
            raise MirrorDeliveryBlocked("mirror_delivery_acl_binding_required")
        if allow_reporting_write and (
                type(canary_approver) is not PinnedTwoOperatorCanaryVerifier
                or canary_approver.db is not db):
            raise MirrorDeliveryBlocked("mirror_canary_operator_gate_required")
        if allow_reporting_write:
            # The service must not be able to sign an operator approval.
            # Distinct pin IDs alone do not prove distinct private keys.
            service_keys = {
                k.public_numbers() for k in verifier.keys.values()
            }
            operator_keys = {
                key.public_numbers()
                for _subject, key in canary_approver.operators.values()
            }
            if service_keys.intersection(operator_keys):
                raise MirrorDeliveryBlocked("mirror_canary_service_key_reused")
        self.db,self.verifier,self.adapter = db,verifier,adapter
        self.canary_approver = canary_approver
        self.allow_reporting_write = allow_reporting_write
        self.acl_metadata = acl_metadata
        self.expected_principal_email = expected_principal_email

    def _current_acl(self, *, now: datetime) -> None:
        """Re-observe both permissions and reporting tab using writer creds.

        Every invocation issues exactly three provider GETs; there is no
        persisted allow-to-write flag or reusable attestation token. These
        checks mitigate but do not eliminate external TOCTOU/ACL changes.
        """
        if not self.allow_reporting_write:
            raise MirrorDeliveryBlocked("mirror_reporting_write_disabled")
        try:
            evidence = read_only_acl_preflight(
                client=self.acl_metadata,
                target=self.adapter.target,
                expected_principal_email=self.expected_principal_email,
                observed_at=now,
            )
            if evidence["status"] != "READ_ONLY_ACL_PASSED_NOT_ACTIVATED":
                raise MirrorDeliveryBlocked("mirror_delivery_acl_unverified")
            if self.adapter.auth_credentials is not self.acl_metadata.credentials:
                raise MirrorDeliveryBlocked("mirror_delivery_acl_binding_changed")
        except Exception:
            raise MirrorDeliveryBlocked("mirror_delivery_acl_unverified") from None

    def _permit(
        self,*,event_id: str,dest: str,token: str,now: datetime,
        live_lease: bool,
    ) -> tuple[str,dict[str,Any],dict[str,Any]]:
        if not isinstance(event_id,str) or SHA.fullmatch(event_id) is None:
            raise MirrorDeliveryBlocked("mirror_delivery_event_invalid")
        outbox = _outbox_head(self.db,event_id)
        _outbox_audit(self.db,event_id,outbox)
        if not outbox or outbox["state"] != "CLAIMED_BLOCKED":
            raise MirrorDeliveryBlocked("mirror_delivery_claim_missing")
        if live_lease and _time(
            outbox["lease_expires_at"],"mirror_delivery_claim_expired"
        ) <= now:
            raise MirrorDeliveryBlocked("mirror_delivery_claim_expired")
        actor,target = self.verifier.verify(
            token=token,destination_id=dest,
            account_id=outbox["account_id"],
            slot_id=outbox["slot_id"],queue_id=outbox["queue_id"],now=now,
        )
        if target != self.adapter.target:
            raise MirrorDeliveryBlocked("mirror_delivery_adapter_not_pinned")
        try:
            preview = _verified_preview(self.db,event_id,outbox)
        except Exception:
            raise MirrorDeliveryBlocked("mirror_delivery_preview_not_current") from None
        return actor,outbox,preview

    def _guard_row(
        self,*,event_id: str,dest: str,row: int,
    ) -> None:
        """One unresolved write claim per provisioned reporting row."""
        entries = self.db.execute(
            """SELECT event_sha256,state FROM sns_mirror_delivery_heads
               WHERE destination_id=? AND row_number=?""",
            (dest,row),
        ).fetchall()
        if any(
            eid != event_id and state in (
                "PREPARED_BLOCKED","OUTCOME_UNKNOWN_BLOCKED","CONFLICT_BLOCKED",
            )
            for eid,state in entries
        ):
            raise MirrorDeliveryBlocked("mirror_delivery_unresolved_row_claim")

    def deliver_once(
        self,*,event_sha256: str,destination_id: str,service_token: str,
        operation_id: str,as_of: datetime | None = None,
        canary_approval_tokens: tuple[str,str] | None = None,
    ) -> dict[str, Any]:
        """One fixed-row write after TWO independent signed approvals.

        Approval signoff consumption and delivery PREPARE commit atomically
        in SQLite. Neither a missing nor replayed approval can reach a
        provider read/PUT. No background auto retry is allowed.
        """
        _database(self.db)
        if not self.allow_reporting_write:
            raise MirrorDeliveryBlocked("mirror_reporting_write_disabled")
        if (not isinstance(operation_id,str) or OP.fullmatch(operation_id) is None
                or len(operation_id) > 90):
            raise MirrorDeliveryBlocked("mirror_delivery_operation_invalid")
        if (not isinstance(canary_approval_tokens, tuple)
                or len(canary_approval_tokens) != 2
                or any(type(x) is not str for x in canary_approval_tokens)):
            raise MirrorDeliveryBlocked("mirror_canary_two_operator_approval_required")
        now = _utc(as_of or datetime.now(timezone.utc),"mirror_delivery_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            actor,outbox,preview = self._permit(
                event_id=event_sha256,dest=destination_id,
                token=service_token,now=now,live_lease=True,
            )
            if _head(self.db,event_sha256,destination_id) is not None:
                raise MirrorDeliveryBlocked("mirror_delivery_already_prepared")
            self._guard_row(
                event_id=event_sha256,dest=destination_id,
                row=self.adapter.target.row_number,
            )
            # Both pinned human signatures are bound to this exact
            # event, queue, operation, destination, row and projection.
            # Replay journal inserts and PREPARE must commit together.
            self.canary_approver.verify_and_consume(
                tokens=canary_approval_tokens,
                event_sha256=event_sha256,
                operation_id=operation_id,
                destination_id=destination_id,
                account_id=outbox["account_id"],
                slot_id=outbox["slot_id"], queue_id=outbox["queue_id"],
                row_number=self.adapter.target.row_number,
                projection_sha256=_hash(preview),
                service_subject=actor, as_of=now,
            )
            prepared = _record(
                self.db,event_id=event_sha256,dest=destination_id,
                account=outbox["account_id"],row=self.adapter.target.row_number,
                projection_sha=_hash(preview),old=None,operation=operation_id,
                action="PREPARE",actor=actor,now=now,
                reason="pinned_reporting_write_attempt",
            )
            self.db.commit()
        except MirrorDeliveryBlocked:
            self.db.rollback()
            raise
        except CanaryApprovalBlocked:
            self.db.rollback()
            raise MirrorDeliveryBlocked("mirror_canary_operator_approval_denied") from None
        except sqlite3.IntegrityError:
            self.db.rollback()
            raise MirrorDeliveryBlocked("mirror_delivery_duplicate_or_replay") from None
        except Exception:
            self.db.rollback()
            raise MirrorDeliveryBlocked("mirror_delivery_prepare_failed") from None

        action,reason,attempted = (
            "OUTCOME_UNKNOWN","response_unverified",False
        )
        try:
            # PREPARED is already committed. ACL uncertainty must never
            # become a no-record/no-claim retry loophole.
            self._current_acl(now=now)
            # A second read-only guard reduces but cannot eliminate external
            # cross-store races. A successful Sheets PUT is not a CAS.
            self._permit(
                event_id=event_sha256,dest=destination_id,
                token=service_token,now=now,live_lease=True,
            )
            observed = self.adapter.read()
            if observed == preview:
                action,reason = "READBACK_VERIFIED","already_identical"
            elif observed is None or (
                observed["account_id"] == preview["account_id"]
                and observed["slot_id"] == preview["slot_id"]
                and observed["queue_id"] == preview["queue_id"]
                and observed["writer_version"] < preview["writer_version"]
            ):
                # Mandatory just-in-time recheck *after* the initial
                # provider read and immediately before the sole PUT.
                self._current_acl(now=now)
                self._permit(
                    event_id=event_sha256,dest=destination_id,
                    token=service_token,now=now,live_lease=True,
                )
                attempted = True
                self.adapter.write_once(preview)
                after = self.adapter.read()
                if after == preview:
                    action,reason = "READBACK_VERIFIED","pinned_readback_matches"
                else:
                    action,reason = "OUTCOME_UNKNOWN","readback_not_verified"
            else:
                action,reason = "CONFLICT","existing_row_conflict"
        except Exception:
            action,reason = "OUTCOME_UNKNOWN","provider_outcome_unknown"
        try:
            self.db.execute("BEGIN IMMEDIATE")
            old = _head(self.db,event_sha256,destination_id)
            _audit(self.db,event_sha256,destination_id,old)
            if (not old or old["state"] != "PREPARED_BLOCKED"
                    or old["last_event_sha256"] != prepared["audit_sha256"]):
                raise MirrorDeliveryBlocked("mirror_delivery_finalize_conflict")
            result = _record(
                self.db,event_id=event_sha256,dest=destination_id,
                account=old["account_id"],row=old["row_number"],
                projection_sha=old["projection_sha256"],old=old,
                operation=operation_id+"_result",action=action,actor=actor,
                now=now,reason=reason,
            )
            self.db.commit()
            result["reporting_write_attempted"] = attempted
            result["reporting_readback_matched"] = action == "READBACK_VERIFIED"
            # The external reporting mirror is NOT the operational queue
            # and cannot ever be used as a publication permission.
            return result
        except MirrorDeliveryBlocked:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            # PREPARED stays durable; never automatically replay the PUT.
            raise MirrorDeliveryBlocked("mirror_delivery_finalize_unknown") from None

    def reconcile_readonly(
        self,*,event_sha256: str,destination_id: str,service_token: str,
        operation_id: str,expected_version: int,expected_audit_sha256: str,
        as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """No writer call even if the missing row might not have been written."""
        _database(self.db)
        if (not isinstance(operation_id,str) or OP.fullmatch(operation_id) is None
                or type(expected_version) is not int
                or not isinstance(expected_audit_sha256,str)):
            raise MirrorDeliveryBlocked("mirror_delivery_reconcile_invalid")
        now = _utc(as_of or datetime.now(timezone.utc),"mirror_delivery_clock_invalid")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            actor,outbox,preview = self._permit(
                event_id=event_sha256,dest=destination_id,
                token=service_token,now=now,live_lease=False,
            )
            old = _head(self.db,event_sha256,destination_id)
            _audit(self.db,event_sha256,destination_id,old)
            if (not old or old["state"] not in (
                    "PREPARED_BLOCKED","OUTCOME_UNKNOWN_BLOCKED",
                ) or old["version"] != expected_version
                    or old["last_event_sha256"] != expected_audit_sha256
                    or old["projection_sha256"] != _hash(preview)
                    or old["row_number"] != self.adapter.target.row_number):
                raise MirrorDeliveryBlocked("mirror_delivery_reconcile_conflict")
            try:
                # Read-only recovery also uses the same scoped credential;
                # a principal that gains operational edit privilege cannot
                # mark a formerly unknown delivery as reconciled.
                self._current_acl(now=now)
                observed = self.adapter.read()
            except Exception:
                raise MirrorDeliveryBlocked("mirror_delivery_readback_unavailable") from None
            if observed is None:
                raise MirrorDeliveryBlocked("mirror_delivery_readback_missing")
            action = "RECONCILE" if observed == preview else "CONFLICT"
            result = _record(
                self.db,event_id=event_sha256,dest=destination_id,
                account=outbox["account_id"],row=old["row_number"],
                projection_sha=old["projection_sha256"],old=old,
                operation=operation_id,action=action,actor=actor,now=now,
                reason="independent_read_only_comparison",
            )
            self.db.commit()
            result["reporting_write_attempted"] = False
            result["reporting_readback_matched"] = action == "RECONCILE"
            return result
        except MirrorDeliveryBlocked:
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise MirrorDeliveryBlocked("mirror_delivery_reconcile_failed") from None

    def inspect(self,*,event_sha256: str,destination_id: str) -> dict[str,Any]:
        _database(self.db)
        if (not isinstance(event_sha256,str) or SHA.fullmatch(event_sha256) is None
                or not isinstance(destination_id,str) or len(destination_id) > 128):
            raise MirrorDeliveryBlocked("mirror_delivery_inspect_invalid")
        head = _head(self.db,event_sha256,destination_id)
        _audit(self.db,event_sha256,destination_id,head)
        return {
            "status":head["state"] if head else "NO_DELIVERY",
            "version":head["version"] if head else 0,
            "audit_sha256":head["last_event_sha256"] if head else ZERO,
            "publish_authorized":False,"operational_queue_modified":False,
        }
