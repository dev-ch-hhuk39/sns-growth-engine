#!/usr/bin/env python3
"""Phase 5B-5B: protected original-proof bytes and append-only verifications.

Provision this SQLite database with owner-only permissions on a protected
volume. It is NOT a substitute for IdP login provisioning, original-rights
investigation, canonical Sheets reads, or an atomic publish authorization.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from build_media_human_review_plan import MEDIA_SLOTS
from build_media_review_approval_receipts import (
    APPROVAL_EVIDENCE, CLIP_EVIDENCE, EVIDENCE_RE, QUEUE_ID_RE,
)
from media_review_trusted_precommit import (
    MAX_CLOCK_SKEW, MAX_EVIDENCE_VERIFICATION_AGE,
    ReviewRequest, SessionVerifier,
    _check_principal, _time, _utc,
)

MIGRATION = Path(__file__).resolve().parents[1] / "db" / "migrations" / "0002_sns_media_review_trust_store.sql"
OP_ID = re.compile(r"evop_[A-Za-z0-9_.:-]{10,100}\Z")
PROOF_MAX_BYTES = 2 * 1024 * 1024
METADATA_FIELDS = frozenset({
    "evidence_id", "kind", "account_id", "slot_id", "queue_id",
    "media_asset_id", "source_id", "usage_scope", "allowed_platforms",
    "allowed_territories", "rights_valid_from", "rights_expires_at",
})


class EvidenceBlocked(ValueError):
    """Stable public reason code; underlying bytes/paths are never logged."""


def initialize_trust_schema(connection: sqlite3.Connection) -> None:
    """Explicit offline/admin migration only. Never called in authorization."""
    if not isinstance(connection, sqlite3.Connection) or connection.in_transaction:
        raise EvidenceBlocked("trust_migration_requires_autocommit")
    connection.executescript(MIGRATION.read_text(encoding="utf-8"))
    connection.execute("PRAGMA foreign_keys = ON")


def _canon(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canon(value).encode("ascii")).hexdigest()


def _metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != METADATA_FIELDS:
        raise EvidenceBlocked("proof_metadata_invalid")
    data = dict(value)
    if (not isinstance(data["evidence_id"], str)
            or not EVIDENCE_RE.fullmatch(data["evidence_id"])
            or data["kind"] not in set(APPROVAL_EVIDENCE) | set(CLIP_EVIDENCE)
            or MEDIA_SLOTS.get((data["account_id"], data["slot_id"])) is None
            or not isinstance(data["queue_id"], str)
            or not QUEUE_ID_RE.fullmatch(data["queue_id"])
            or any(not isinstance(data[field], str)
                   or not re.fullmatch(r"[A-Za-z0-9_.:-]{3,128}", data[field])
                   for field in ("source_id", "media_asset_id"))
            or data["usage_scope"] != "THREADS_ORGANIC_ONLY"
            or data["allowed_platforms"] != ["threads"]
            or not isinstance(data["allowed_territories"], list)
            or "JP" not in data["allowed_territories"]
            or any(not isinstance(x, str) for x in data["allowed_territories"])):
        raise EvidenceBlocked("proof_scope_invalid")
    try:
        start = datetime.fromisoformat(data["rights_valid_from"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(data["rights_expires_at"].replace("Z", "+00:00"))
        start = _utc(start, "proof_time_invalid")
        end = _utc(end, "proof_time_invalid")
        if start >= end:
            raise EvidenceBlocked("proof_time_invalid")
    except (TypeError, ValueError, AttributeError, OverflowError):
        raise EvidenceBlocked("proof_time_invalid") from None
    return data


def _authorize(
    bearer: str, *, verifier: SessionVerifier, issuer: str,
    account_id: str, slot_id: str, queue_id: str, now: datetime,
) -> str:
    if (not isinstance(bearer, str) or not bearer.startswith("Bearer ")
            or len(bearer.split()) != 2 or verifier is None):
        raise EvidenceBlocked("proof_reviewer_unavailable")
    request = ReviewRequest(
        account_id=account_id, slot_id=slot_id, queue_id=queue_id,
        expected_queue_revision="not_a_queue_revision",
        expected_plan_sha256="0" * 64, expected_receipts_head_sha256="0" * 64,
        draft_event_sha256="0" * 64, confirm_human_review=True,
    )
    try:
        principal = verifier.verify(bearer[7:], now=now)
        principal = _check_principal(principal, request, now, issuer)
    except Exception:
        raise EvidenceBlocked("proof_reviewer_unavailable") from None
    return principal.subject


class ProtectedEvidenceVault:
    """Separate, append-only rights proof store. Original bytes verified on read."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        if not isinstance(connection, sqlite3.Connection):
            raise EvidenceBlocked("protected_store_unavailable")
        self.connection = connection

    def _events(self, evidence_id: str) -> list[tuple[Any, ...]]:
        try:
            rows = self.connection.execute(
                """SELECT revision,operation_id,action,metadata_json,original_bytes,
                          original_sha256,previous_event_sha256,event_sha256,
                          reviewer_subject,created_at
                   FROM sns_review_evidence_events
                   WHERE evidence_id=? ORDER BY revision""", (evidence_id,),
            ).fetchall()
        except sqlite3.Error:
            raise EvidenceBlocked("protected_store_unavailable") from None
        previous = "0" * 64
        for number, row in enumerate(rows, 1):
            revision, op, action, meta_json, content, digest, prev, event_hash, actor, created = row
            if revision != number or prev != previous or action not in ("VERIFY", "REVOKE"):
                raise EvidenceBlocked("proof_history_invalid")
            if (number == 1 and action != "VERIFY") or (number > 1 and action != "REVOKE"):
                raise EvidenceBlocked("proof_history_invalid")
            if not isinstance(content, bytes) or hashlib.sha256(content).hexdigest() != digest:
                raise EvidenceBlocked("proof_bytes_tampered")
            try:
                metadata = json.loads(meta_json)
                if _canon(_metadata(metadata)) != meta_json:
                    raise EvidenceBlocked("proof_metadata_tampered")
            except (TypeError, ValueError):
                raise EvidenceBlocked("proof_metadata_tampered") from None
            payload = {
                "evidence_id": evidence_id, "revision": revision,
                "operation_id": op, "action": action,
                "metadata_json": meta_json, "original_sha256": digest,
                "previous_event_sha256": prev, "reviewer_subject": actor,
                "created_at": created,
            }
            if event_hash != _hash(payload):
                raise EvidenceBlocked("proof_history_tampered")
            previous = event_hash
        return rows

    def _write(
        self, *, evidence_id: str, action: str, metadata: dict[str, Any],
        original: bytes, actor: str, operation_id: str,
        expected_revision: int, now: datetime,
    ) -> int:
        if (not isinstance(operation_id, str) or not OP_ID.fullmatch(operation_id)
                or type(expected_revision) is not int
                or not 0 <= expected_revision <= 1
                or self.connection.in_transaction):
            raise EvidenceBlocked("proof_operation_invalid")
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            if self.connection.execute(
                "SELECT 1 FROM sns_review_evidence_events WHERE operation_id=?",
                (operation_id,),
            ).fetchone():
                raise EvidenceBlocked("proof_operation_replayed")
            rows = self._events(evidence_id)
            if len(rows) != expected_revision:
                raise EvidenceBlocked("proof_revision_changed")
            if (action == "VERIFY" and rows) or (action == "REVOKE" and len(rows) != 1):
                raise EvidenceBlocked("proof_lifecycle_invalid")
            previous = rows[-1][7] if rows else "0" * 64
            revision = len(rows) + 1
            digest = hashlib.sha256(original).hexdigest()
            meta_json = _canon(metadata)
            created = now.isoformat(timespec="seconds")
            payload = {
                "evidence_id": evidence_id, "revision": revision,
                "operation_id": operation_id, "action": action,
                "metadata_json": meta_json, "original_sha256": digest,
                "previous_event_sha256": previous, "reviewer_subject": actor,
                "created_at": created,
            }
            self.connection.execute(
                """INSERT INTO sns_review_evidence_events
                   (evidence_id,revision,operation_id,action,metadata_json,
                    original_bytes,original_sha256,previous_event_sha256,
                    event_sha256,reviewer_subject,created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (evidence_id, revision, operation_id, action, meta_json,
                 original, digest, previous, _hash(payload), actor, created),
            )
            self.connection.commit()
        except EvidenceBlocked:
            self.connection.rollback()
            raise
        except Exception:
            self.connection.rollback()
            raise EvidenceBlocked("proof_storage_failed") from None
        return revision

    def attest(
        self, *, metadata: dict[str, Any], original_bytes: bytes,
        human_verified_original: bool, bearer_token: str,
        verifier: SessionVerifier, trusted_issuer: str,
        operation_id: str, as_of: datetime | None = None,
    ) -> int:
        """Only an authenticated reviewer can attest that original proof was checked.

        A frontend checkbox, supplied metadata or a local JSON 'VERIFIED' is
        never sufficient. The host must keep vault/session DB inaccessible to
        clients and ensure the reviewer actually inspected the original.
        """
        now = _utc(as_of or datetime.now(timezone.utc), "proof_clock_invalid")
        meta = _metadata(metadata)
        if (human_verified_original is not True or not isinstance(original_bytes, bytes)
                or not 1 <= len(original_bytes) <= PROOF_MAX_BYTES):
            raise EvidenceBlocked("proof_original_not_verified")
        actor = _authorize(
            bearer_token, verifier=verifier, issuer=trusted_issuer,
            account_id=meta["account_id"], slot_id=meta["slot_id"],
            queue_id=meta["queue_id"], now=now,
        )
        return self._write(
            evidence_id=meta["evidence_id"], action="VERIFY",
            metadata=meta, original=original_bytes, actor=actor,
            operation_id=operation_id, expected_revision=0, now=now,
        )

    def revoke(
        self, *, evidence_id: str, bearer_token: str,
        verifier: SessionVerifier, trusted_issuer: str, operation_id: str,
        expected_revision: int, as_of: datetime | None = None,
    ) -> int:
        now = _utc(as_of or datetime.now(timezone.utc), "proof_clock_invalid")
        rows = self._events(evidence_id)
        if not rows:
            raise EvidenceBlocked("proof_missing")
        meta = _metadata(json.loads(rows[0][3]))
        actor = _authorize(
            bearer_token, verifier=verifier, issuer=trusted_issuer,
            account_id=meta["account_id"], slot_id=meta["slot_id"],
            queue_id=meta["queue_id"], now=now,
        )
        return self._write(
            evidence_id=evidence_id, action="REVOKE", metadata=meta,
            original=rows[0][4], actor=actor, operation_id=operation_id,
            expected_revision=expected_revision, now=now,
        )

    def get_current(self, evidence_id: str) -> dict[str, Any]:
        if not isinstance(evidence_id, str) or not EVIDENCE_RE.fullmatch(evidence_id):
            raise EvidenceBlocked("proof_reference_invalid")
        rows = self._events(evidence_id)
        if not rows:
            raise EvidenceBlocked("proof_missing")
        meta = _metadata(json.loads(rows[0][3]))
        if any(row[3] != rows[0][3] or row[5] != rows[0][5] for row in rows):
            raise EvidenceBlocked("proof_history_invalid")
        current = rows[-1]
        return {
            **meta,
            "verification_status": "VERIFIED",
            "revoked": current[2] == "REVOKE",
            "original_reference_verified": True,
            "verified_at": rows[0][9],
        }

    def read_original_scoped(
        self, *, evidence_id: str, account_id: str, slot_id: str,
        queue_id: str, bearer_token: str, verifier: SessionVerifier,
        trusted_issuer: str, as_of: datetime | None = None,
    ) -> bytes:
        """Fetch original bytes for a verified, in-scope human-review session.

        Only call after checking evidence_id belongs to the *current* draft.
        The caller must serve a no-store, attachment-only, no-sniff response.
        The method never emits a source URL, token, or raw proof in logs.
        """
        now = _utc(as_of or datetime.now(timezone.utc), "proof_clock_invalid")
        _authorize(
            bearer_token, verifier=verifier, issuer=trusted_issuer,
            account_id=account_id, slot_id=slot_id, queue_id=queue_id, now=now,
        )
        record = self.get_current(evidence_id)
        if (record["account_id"], record["slot_id"], record["queue_id"]) != (
            account_id, slot_id, queue_id,
        ) or record.get("revoked") is not False:
            raise EvidenceBlocked("proof_scope_or_revocation_invalid")
        try:
            start = _time(record["rights_valid_from"], "proof_rights_invalid")
            expiry = _time(record["rights_expires_at"], "proof_rights_invalid")
            checked = _time(record["verified_at"], "proof_verification_invalid")
            if (not start <= now < expiry
                    or checked > now + MAX_CLOCK_SKEW
                    or now - checked > MAX_EVIDENCE_VERIFICATION_AGE):
                raise EvidenceBlocked("proof_expired_or_unverified")
        except (TypeError, ValueError):
            raise EvidenceBlocked("proof_expired_or_unverified") from None
        original = self._events(evidence_id)[0][4]
        if not isinstance(original, bytes) or not 1 <= len(original) <= PROOF_MAX_BYTES:
            raise EvidenceBlocked("proof_bytes_invalid")
        return original
