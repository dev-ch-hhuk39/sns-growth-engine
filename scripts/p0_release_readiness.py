#!/usr/bin/env python3
"""Single local P0 readiness check: two captures -> shadow -> blocked CAS.

Combines the existing 6AH/6AI/6AJ checks with the *existing* local P0 CAS
journal. No adapter connects this module to a live publisher or Sheets writer.
Even a perfectly successful rehearsal is never an operational release permit.
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from datetime import datetime
from typing import Any

from p0_pair_shadow_parity import (
    P0PairBlocked, compare_snapshots, initialize_ephemeral_shadow,
    stage_in_ephemeral_sqlite,
)
from p0_snapshot_cutover_preflight import (
    P0PreflightBlocked, inspect,
)

SCHEMA = "sns_p0_release_readiness_offline_v1"
MAX_REHEARSAL_CANDIDATES = 256
HARD_BLOCKERS = (
    "OPERATOR_APPROVED_SINGLE_WRITER_CUTOVER_MISSING",
    "SIGNED_PROVIDER_EXPORT_AND_COMPLETE_SOURCE_UNPROVEN",
    "LEGACY_AND_EXTERNAL_WRITER_FREEZE_NOT_ATTESTED",
    "PRODUCTION_BACKUP_RESTORE_NOT_VERIFIED",
    "LIVE_POST_AND_MEDIA_RIGHTS_CANARY_NOT_VERIFIED",
    "POSTED_RESULT_RECONCILIATION_NOT_VERIFIED",
    "24H_72H_168H_PRODUCTION_FEEDBACK_MISSING",
)


class P0ReleaseBlocked(ValueError):
    """Fixed reason codes only; input data must never appear in exceptions."""


def _base() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "CUTOVER_BLOCKED",
        "local_rehearsal_status": "NOT_PROVEN",
        "shadow_status": "NOT_STAGED",
        "cas_status": "NOT_TESTED",
        "provider_call_count": 0,
        "external_write_count": 0,
        "operational_db_write_count": 0,
        "production_cutover_authorized": False,
        "publish_authorized": False,
        "media_rights_verified": False,
        "sheets_write_authorized": False,
        "operational_sqlite_write_authorized": False,
        "external_writers_frozen": False,
        "source_provenance": "UNATTESTED_OFFLINE_METADATA_ONLY",
        "ready_candidate_count": 0,
        "cas_unknown_outcome_quarantined_count": 0,
        "legacy_p0_mutation_calls_remaining": None,
        "legacy_all_mutation_calls_remaining": None,
        "findings": [],
        "mandatory_production_blockers": list(HARD_BLOCKERS),
    }


def _legacy_counts(plan: dict[str, Any]) -> tuple[int, int]:
    """Consume the existing AST inventory classification, never an allowlist."""
    if (type(plan) is not dict or plan.get("status") != "CUTOVER_BLOCKED"
            or plan.get("release_approval") is not False
            or plan.get("operational_source_selected") is not False
            or type(plan.get("mutation_sites")) is not int
            or type(plan.get("not_migrated_sites")) is not int
            or type(plan.get("workstream_counts")) is not dict):
        raise P0ReleaseBlocked("P0_RELEASE_LEGACY_INVENTORY_INVALID")
    counts = plan["workstream_counts"]
    if (any(type(v) is not int or v < 0 for v in counts.values())
            or any(type(k) is not str or not k.startswith(("P0_", "P1_", "P2_"))
                   for k in counts)
            or sum(counts.values()) != plan["mutation_sites"]
            or plan["mutation_sites"] != plan["not_migrated_sites"]):
        raise P0ReleaseBlocked("P0_RELEASE_LEGACY_INVENTORY_INCONSISTENT")
    return (sum(count for label, count in counts.items() if label.startswith("P0_")),
            plan["not_migrated_sites"])


def _get_cas_module():
    try:
        import p0_queue_cas_rehearsal as module
    except ImportError:
        raise P0ReleaseBlocked("P0_CAS_LOCAL_MODULE_UNAVAILABLE") from None
    return module


def run_rehearsal(
    before: dict[str, Any], after: dict[str, Any], *, as_of: datetime,
    legacy_plan: dict[str, Any], cas_module: Any = None,
) -> dict[str, Any]:
    """Exercise local cross-module flow; never touch provider/operational DB.

    All database connections are fresh SQLite :memory: and discarded on exit.
    The caller's snapshots are inspected (not modified) by existing modules.
    `cas_module` is injectible for isolated unit tests; the real CLI MUST use
    the existing p0_queue_cas_rehearsal module in the actual checkout.
    """
    result = _base()
    p0_remaining, all_remaining = _legacy_counts(legacy_plan)
    result["legacy_p0_mutation_calls_remaining"] = p0_remaining
    result["legacy_all_mutation_calls_remaining"] = all_remaining
    try:
        check = compare_snapshots(
            before, after, as_of=as_of, legacy_writer_sites=all_remaining,
        )
        result["pair_status"] = check.report["pair_status"]
        result["pair_findings"] = sorted(set(check.report["findings"]))
        result["queue_rows_count"] = check.report["queue_rows"]
        result["posted_rows_count"] = check.report["posted_rows"]
        if check.report["pair_status"] != "PASS_LOCAL_METADATA_ONLY":
            result["findings"] = ["P0_RELEASE_PAIR_FAILED"]
            return result
        # Parse READY scope through 6AH; snapshots have NO authenticated
        # content/rights proof. The local CAS merely simulates uncertainty.
        candidates = inspect(
            after, as_of=as_of, legacy_writer_sites=all_remaining,
        ).candidates
        result["ready_candidate_count"] = len(candidates)
        if len(candidates) > MAX_REHEARSAL_CANDIDATES:
            result["findings"] = ["P0_RELEASE_REHEARSAL_SCOPE_TOO_LARGE"]
            return result
        # Existing 6AJ import rejects disk DBs and ATTACH. Never substitute
        # a user path for a memory connection.
        with closing(sqlite3.connect(":memory:", isolation_level=None)) as shadow:
            shadow.execute("PRAGMA foreign_keys=ON")
            initialize_ephemeral_shadow(shadow, explicitly_for_tests=True)
            staged = stage_in_ephemeral_sqlite(
                check, shadow, as_of=as_of,
                explicit_temporary_rehearsal=True,
            )
            if (staged.get("shadow_status") != "VERIFIED_TEMPORARY_METADATA_ONLY"
                    or staged.get("shadow_manifest_verified") is not True
                    or staged.get("production_cutover_authorized") is not False
                    or staged.get("publish_authorized") is not False):
                raise P0ReleaseBlocked("P0_RELEASE_SHADOW_NOT_VERIFIED")
            result["shadow_status"] = "PASS_LOCAL_MEMORY_ONLY"
        if not candidates:
            result["cas_status"] = "NOT_EXERCISED_NO_READY_CANDIDATES"
            result["findings"] = ["P0_RELEASE_NO_READY_TEXT_CANDIDATES"]
            return result
        module = cas_module if cas_module is not None else _get_cas_module()
        with closing(sqlite3.connect(":memory:", isolation_level=None)) as cas_db:
            cas_db.execute("PRAGMA foreign_keys=ON")
            module.initialize_rehearsal_schema(
                cas_db, explicit_local_test_only=True,
            )
            ledger = module.P0QueueRehearsal(cas_db)
            for account, queue_id, source_sha256 in candidates:
                # Each synthetic candidate has an independent unique op ID.
                # Never include IDs in output or caught exception strings.
                token = hashlib.sha256(
                    (account + "\x00" + queue_id).encode("utf-8"),
                ).hexdigest()[:30]
                base = dict(account_id=account, queue_id=queue_id)
                observed = ledger.observe(
                    **base, platform="threads", source_sha256=source_sha256,
                    observed_at=check.last_observed_at, as_of=as_of,
                    operation_id="p0_observe_" + token,
                )
                if (observed.get("status") != "OBSERVED_BLOCKED"
                        or observed.get("publish_authorized") is not False
                        or observed.get("sheets_write_allowed") is not False):
                    raise P0ReleaseBlocked("P0_RELEASE_CAS_OBSERVE_UNSAFE")
                claimed = ledger.claim(
                    **base, operation_id="p0_claim_" + token,
                    expected_revision=observed["revision"],
                    expected_head_sha256=observed["head_sha256"],
                    expected_source_sha256=source_sha256, as_of=as_of,
                )
                if (claimed.get("status") != "CLAIMED_BLOCKED"
                        or claimed.get("dispatch_allowed") is not False
                        or claimed.get("publish_authorized") is not False
                        or claimed.get("sheets_write_allowed") is not False):
                    raise P0ReleaseBlocked("P0_RELEASE_CAS_CLAIM_UNSAFE")
                unknown = ledger.quarantine(
                    **base, operation_id="p0_uncertain_" + token,
                    expected_revision=claimed["revision"],
                    expected_head_sha256=claimed["head_sha256"],
                    reason="ACK_UNKNOWN", as_of=as_of,
                )
                if (unknown.get("status") != "OUTCOME_UNKNOWN_BLOCKED"
                        or unknown.get("publish_authorized") is not False
                        or unknown.get("dispatch_allowed") is not False
                        or unknown.get("sheets_write_allowed") is not False
                        or ledger.inspect(queue_id=queue_id)["status"]
                        != "OUTCOME_UNKNOWN_BLOCKED"):
                    raise P0ReleaseBlocked("P0_RELEASE_CAS_UNKNOWN_UNSAFE")
                try:
                    ledger.claim(
                        **base, operation_id="p0_retry_" + token,
                        expected_revision=unknown["revision"],
                        expected_head_sha256=unknown["head_sha256"],
                        expected_source_sha256=source_sha256, as_of=as_of,
                    )
                except module.P0RehearsalBlocked:
                    pass
                else:
                    raise P0ReleaseBlocked("P0_RELEASE_CAS_RETRY_NOT_BLOCKED")
                result["cas_unknown_outcome_quarantined_count"] += 1
        result["cas_status"] = "PASS_LOCAL_BLOCKED_CAS_ONLY"
        result["local_rehearsal_status"] = "PASS_LOCAL_NOT_PRODUCTION"
        return result
    except (P0PairBlocked, P0PreflightBlocked, sqlite3.Error):
        # Existing modules raise fixed codes but never assume third-party
        # errors may be copied into user-visible reports.
        result["findings"] = ["P0_RELEASE_SOURCE_OR_STORAGE_UNVERIFIABLE"]
        return result
    except P0ReleaseBlocked as exc:
        result["findings"] = [str(exc)]
        return result
    except Exception:
        # Unknown provider-like or future implementation exception. Fail
        # closed; suppress message to avoid exposing secrets or filenames.
        result["findings"] = ["P0_RELEASE_LOCAL_INTEGRATION_UNVERIFIABLE"]
        return result
