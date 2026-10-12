#!/usr/bin/env python3
"""Phase 5B-6L: read-only mirror canary classification, never a write permit.

Runs Drive/Sheets GET metadata ACL inspection using the very same credential
object bound to the gspread worksheet client, then one fixed-row GET.
Cannot create a Sheet, update a row, alter SQLite state, ACK delivery or post.
The result is a *decision-support preview* subject to operator acceptance.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any

from media_mirror_delivery_identity import PinnedLiveMirrorServiceVerifier
from media_mirror_outbox import (
    SHA, _audit as _outbox_audit, _head as _outbox_head,
    _projection_for as _verified_preview,
)
from media_mirror_readonly_acl_preflight import (
    ReadOnlyGoogleMirrorMetadata, read_only_acl_preflight,
)
from media_mirror_sheets_adapter import GspreadReportingFixedRow
from media_publish_intent_authority import _database
from media_review_trusted_precommit import _time, _utc
from media_review_verified_identity import SAFE_NAME


class MirrorReadOnlyCanaryBlocked(ValueError):
    """Sanitized failure code, never secrets or untrusted provider payloads."""


class MirrorReadOnlyCanary:
    """Explicit read-only opt-in with bound provider credentials and account."""

    def __init__(
        self, *, db: sqlite3.Connection,
        verifier: PinnedLiveMirrorServiceVerifier,
        metadata: ReadOnlyGoogleMirrorMetadata,
        adapter: GspreadReportingFixedRow,
        expected_principal_email: str,
        allow_provider_reads: bool = False,
    ) -> None:
        if (not isinstance(db, sqlite3.Connection)
                or type(verifier) is not PinnedLiveMirrorServiceVerifier
                or verifier.db is not db
                or type(metadata) is not ReadOnlyGoogleMirrorMetadata
                or type(adapter) is not GspreadReportingFixedRow
                or adapter.auth_credentials is None
                or adapter.auth_credentials is not metadata.credentials
                or not isinstance(expected_principal_email, str)
                or expected_principal_email != metadata.principal_email
                or type(allow_provider_reads) is not bool):
            raise MirrorReadOnlyCanaryBlocked("mirror_canary_binding_invalid")
        self.db = db
        self.verifier = verifier
        self.metadata = metadata
        self.adapter = adapter
        self.expected_principal_email = expected_principal_email
        self.allow_provider_reads = allow_provider_reads

    def inspect(
        self, *, event_sha256: str, destination_id: str,
        service_token: str, as_of: datetime | None = None,
    ) -> dict[str, Any]:
        """No DB mutations and no provider PUT under any circumstances."""
        if not self.allow_provider_reads:
            raise MirrorReadOnlyCanaryBlocked("mirror_canary_reads_disabled")
        _database(self.db)
        if (not isinstance(event_sha256, str)
                or SHA.fullmatch(event_sha256) is None
                or not isinstance(destination_id, str)
                or SAFE_NAME.fullmatch(destination_id) is None):
            raise MirrorReadOnlyCanaryBlocked("mirror_canary_identifier_invalid")
        now = _utc(
            as_of or datetime.now(timezone.utc), "mirror_canary_clock_invalid"
        )
        before = self.db.total_changes
        try:
            outbox = _outbox_head(self.db, event_sha256)
            _outbox_audit(self.db, event_sha256, outbox)
            if not outbox or outbox["state"] != "CLAIMED_BLOCKED":
                raise MirrorReadOnlyCanaryBlocked("mirror_canary_claim_missing")
            if _time(
                outbox["lease_expires_at"], "mirror_canary_claim_expired"
            ) <= now:
                raise MirrorReadOnlyCanaryBlocked("mirror_canary_claim_expired")
            _actor, target = self.verifier.verify(
                token=service_token, destination_id=destination_id,
                account_id=outbox["account_id"],
                slot_id=outbox["slot_id"],
                queue_id=outbox["queue_id"], now=now,
            )
            if target != self.adapter.target:
                raise MirrorReadOnlyCanaryBlocked(
                    "mirror_canary_target_not_pinned"
                )
            preview = _verified_preview(self.db, event_sha256, outbox)
            # Existing PREPARED/UNKNOWN/CONFLICT deliveries in this fixed
            # row must be reconciled separately, never called 'safe to sync'.
            unresolved = self.db.execute(
                """SELECT 1 FROM sns_mirror_delivery_heads
                   WHERE destination_id=? AND row_number=?
                     AND event_sha256<>?
                     AND state IN (
                        'PREPARED_BLOCKED','OUTCOME_UNKNOWN_BLOCKED',
                        'CONFLICT_BLOCKED'
                     ) LIMIT 1""",
                (destination_id, target.row_number, event_sha256),
            ).fetchone()
            if unresolved:
                raise MirrorReadOnlyCanaryBlocked(
                    "mirror_canary_unresolved_prior_delivery"
                )
            evidence = read_only_acl_preflight(
                client=self.metadata, target=target,
                expected_principal_email=self.expected_principal_email,
                observed_at=now,
            )
            # Only now, after proving metadata for the same credential
            # object, perform the exact A<row>:L<row> reporting GET.
            observed = self.adapter.read()
            if observed == preview:
                state = "MATCHED_BLOCKED"
            elif observed is None:
                state = "EMPTY_REQUIRES_APPROVAL_BLOCKED"
            elif (
                observed["account_id"] == preview["account_id"]
                and observed["slot_id"] == preview["slot_id"]
                and observed["queue_id"] == preview["queue_id"]
                and observed["writer_version"] < preview["writer_version"]
            ):
                state = "OLDER_REQUIRES_APPROVAL_BLOCKED"
            else:
                state = "CONFLICT_BLOCKED"
            if self.db.total_changes != before:
                raise MirrorReadOnlyCanaryBlocked(
                    "mirror_canary_db_mutation_detected"
                )
            return {
                "status": state,
                "acl_check": evidence["status"],
                "acl_evidence_sha256": evidence["evidence_sha256"],
                "source_version": preview["writer_version"],
                "observed_version": (
                    observed["writer_version"] if observed else None
                ),
                "provider_read_only": True,
                "reporting_write_authorized": False,
                "reporting_write_executed": False,
                "sqlite_mutated": False,
                "operational_queue_modified": False,
                "sns_publish_authorized": False,
                "requires_separate_operator_approval": True,
            }
        except MirrorReadOnlyCanaryBlocked:
            raise
        except Exception:
            # Even provider errors are sanitized; do not leak response
            # bodies, credential details, captions or worksheet values.
            raise MirrorReadOnlyCanaryBlocked(
                "mirror_canary_evidence_unavailable"
            ) from None
