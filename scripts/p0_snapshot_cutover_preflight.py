#!/usr/bin/env python3
"""P0 offline metadata snapshot preflight; does not grant posting authority.

Consumes the exact minimal-metadata schema from audit_queue_authority_cutover.
Only read-only planning and *synthetic temporary SQLite rehearsal* are allowed.
No real Sheets, SNS or live operational database mutation is supported.

Important: A snapshot (including any digest we derive from it) is not
cryptographically attested by Google Sheets, and contains no content proof.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

SCHEMA = "sns_operational_queue_offline_metadata_v1"
REPORT_SCHEMA = "sns_p0_snapshot_preflight_v1"
ACTIVE_P0 = frozenset({"night_scout", "liver_manager"})
KNOWN_ACCOUNTS = ACTIVE_P0 | {"beauty_account"}
TERMINAL_UNCERTAIN = frozenset({
    "PROCESSING", "POSTED_SAVE_FAILED", "POSTED_SAVE_UNVERIFIED",
    "PUBLISH_OUTCOME_UNVERIFIED",
})
VALID_STATES = frozenset({
    "WAITING_REVIEW", "READY", "PLANNED", "DRAFT", "REJECTED",
    "PROCESSING", "POSTED", "FAILED", "DUPLICATE_BLOCKED",
    "POSTED_SAVE_FAILED", "POSTED_SAVE_UNVERIFIED", "PUBLISH_OUTCOME_UNVERIFIED",
    "BLOCKED_INTERNAL_LEAK", "SAFETY_STOP_HYBRID_AI_GATE",
})
ALLOWED_QUEUE_KEYS = frozenset({
    "queue_id", "account_id", "slot_id", "platform", "status",
    "media_required", "media_asset_id", "media_type", "publisher_media_type",
    "content_type", "generation_mode", "content_route", "has_media",
})
ALLOWED_POST_KEYS = frozenset({
    "queue_id", "account_id", "status", "real_post", "verification_status",
    "external_post_id",
})
MAX_ITEMS = 10_000
REHEARSAL_QUEUE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,120}\Z")
MEDIA_BOOLEAN_MARKERS = frozenset({"true", "false", "1", "0", "yes", "no"})
MAX_AGE = timedelta(minutes=5)
OBSERVE_MAX_AGE = timedelta(seconds=90)
FUTURE_SKEW = timedelta(seconds=120)


class P0PreflightBlocked(ValueError):
    """Sanitized reason code only; never includes source data."""


def _now(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise P0PreflightBlocked("P0_CLOCK_NOT_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise P0PreflightBlocked("P0_SNAPSHOT_TIMESTAMP_INVALID")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise P0PreflightBlocked("P0_SNAPSHOT_TIMESTAMP_INVALID") from None
    return _now(result)


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value, ensure_ascii=True, sort_keys=True,
            separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError, OverflowError):
        raise P0PreflightBlocked("P0_SNAPSHOT_JSON_INVALID") from None


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("ascii")).hexdigest()


def _identity(row: Mapping[str, Any]) -> str:
    # SHA of metadata identity, *never* a raw queue ID in output.
    return _digest([
        str(row.get("account_id", "")), str(row.get("queue_id", "")),
    ])[:20]


def _is_true(value: Any) -> bool:
    return value is True or (
        isinstance(value, str) and value.strip().lower() in {"true", "1", "yes"}
    )


def _media(row: Mapping[str, Any]) -> bool:
    return (
        _is_true(row.get("media_required"))
        or _is_true(row.get("has_media"))
        or bool(str(row.get("media_asset_id") or "").strip())
        or str(row.get("publisher_media_type") or "").strip().lower()
        not in {"", "text", "none"}
        or str(row.get("media_type") or "").strip().lower()
        not in {"", "text", "none"}
    )


def _check_rows(snapshot: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "schema", "observed_at", "queue_rows", "posted_rows",
    } or snapshot.get("schema") != SCHEMA:
        raise P0PreflightBlocked("P0_SNAPSHOT_SCHEMA_INVALID")
    out: list[list[dict[str, Any]]] = []
    for key, columns in (
        ("queue_rows", ALLOWED_QUEUE_KEYS), ("posted_rows", ALLOWED_POST_KEYS),
    ):
        rows = snapshot[key]
        if type(rows) is not list or len(rows) > MAX_ITEMS:
            raise P0PreflightBlocked("P0_SNAPSHOT_ROW_LIMIT_INVALID")
        cleaned = []
        for row in rows:
            if (type(row) is not dict or not set(row).issubset(columns)
                    or not all(type(v) in {str, bool} for v in row.values())):
                raise P0PreflightBlocked("P0_SNAPSHOT_UNSAFE_COLUMNS")
            cleaned.append(row)
        out.append(cleaned)
    return out[0], out[1]


@dataclass(frozen=True)
class Preflight:
    """Private candidates are never included in the serialized public report."""
    report: dict[str, Any]
    candidates: tuple[tuple[str, str, str], ...]  # account, queue ID, source hash
    observed_at: datetime


def inspect(snapshot: dict[str, Any], *, as_of: datetime,
            legacy_writer_sites: int) -> Preflight:
    """Inspect one source-export snapshot without any writes or provider calls."""
    now = _now(as_of)
    if type(legacy_writer_sites) is not int or legacy_writer_sites < 0:
        raise P0PreflightBlocked("P0_WRITER_INVENTORY_UNTRUSTED")
    queues, posts = _check_rows(snapshot)
    observed = _timestamp(snapshot["observed_at"])
    age = now - observed
    problems: set[tuple[str, str]] = set()

    def add(code: str, row: Mapping[str, Any] | None = None) -> None:
        problems.add((code, _identity(row) if row is not None else ""))

    if not -FUTURE_SKEW <= age <= MAX_AGE:
        add("P0_OFFLINE_SNAPSHOT_STALE_OR_FUTURE")

    queue_by_id: dict[str, list[dict[str, Any]]] = {}
    for row in queues:
        qid = str(row.get("queue_id", "")).strip()
        account = str(row.get("account_id", "")).strip()
        if not qid or not account:
            add("P0_QUEUE_IDENTITY_MISSING", row)
            continue
        queue_by_id.setdefault(qid, []).append(row)
        if not REHEARSAL_QUEUE_ID.fullmatch(qid):
            add("P0_QUEUE_ID_NOT_REHEARSAL_SAFE", row)
        if account not in KNOWN_ACCOUNTS:
            add("P0_ACCOUNT_UNKNOWN", row)
        if account == "beauty_account":
            add("P0_BEAUTY_ACCOUNT_NOT_IN_REHEARSAL_SCOPE", row)
        if str(row.get("platform", "")).strip().lower() != "threads":
            add("P0_PLATFORM_NOT_IN_SCOPE", row)
        status = str(row.get("status", "")).strip().upper()
        if status not in VALID_STATES:
            add("P0_QUEUE_STATUS_INVALID", row)
        if status in TERMINAL_UNCERTAIN:
            add("P0_EXISTING_OUTCOME_UNVERIFIED", row)
        if status == "READY" and not str(row.get("slot_id", "")).strip():
            add("P0_READY_SLOT_MISSING", row)
        if status == "READY" and (
            "media_required" not in row or
            str(row.get("media_required", "")).strip().lower()
            not in MEDIA_BOOLEAN_MARKERS
        ):
            add("P0_READY_MEDIA_SCOPE_UNDECLARED", row)
        if status == "READY" and "has_media" in row and (
            str(row["has_media"]).strip().lower()
            not in MEDIA_BOOLEAN_MARKERS
        ):
            add("P0_READY_MEDIA_SCOPE_UNDECLARED", row)
        if status == "READY" and _media(row):
            add("P0_MEDIA_RIGHTS_NOT_IN_METADATA", row)
    for matching in queue_by_id.values():
        if len(matching) != 1:
            add("P0_GLOBAL_QUEUE_ID_COLLISION", matching[0])

    posts_by_queue: dict[str, list[dict[str, Any]]] = {}
    posts_by_external: dict[str, list[dict[str, Any]]] = {}
    for row in posts:
        qid = str(row.get("queue_id", "")).strip()
        account = str(row.get("account_id", "")).strip()
        external = str(row.get("external_post_id", "")).strip()
        if not qid or not account:
            add("P0_POST_IDENTITY_MISSING", row)
            continue
        posts_by_queue.setdefault(qid, []).append(row)
        if external:
            posts_by_external.setdefault(external, []).append(row)
        associated = queue_by_id.get(qid, [])
        if len(associated) != 1:
            add("P0_POST_ORPHAN_OR_AMBIGUOUS", row)
        elif str(associated[0].get("account_id", "")) != account:
            add("P0_POST_CROSS_ACCOUNT", associated[0])
        if str(row.get("status", "")).strip().upper() != "POSTED":
            add("P0_POST_RESULT_STATUS_UNVERIFIED", row)
        if (not external or not _is_true(row.get("real_post"))
                or str(row.get("verification_status", "")).strip().upper()
                != "READ_AFTER_WRITE_PASS"):
            add("P0_POST_RESULT_PROOF_MISSING", row)
    for matching in posts_by_queue.values():
        if len(matching) != 1:
            add("P0_POST_RESULT_DUPLICATE_QUEUE", matching[0])
    for matching in posts_by_external.values():
        if len(matching) != 1:
            add("P0_EXTERNAL_POST_ID_COLLISION", matching[0])
    for row in queues:
        qid = str(row.get("queue_id", "")).strip()
        posted = posts_by_queue.get(qid, [])
        status = str(row.get("status", "")).strip().upper()
        if status == "POSTED" and len(posted) != 1:
            add("P0_POSTED_QUEUE_RESULT_NOT_UNIQUE", row)
        if status != "POSTED" and posted:
            add("P0_POST_WITH_NONPOSTED_QUEUE", row)

    # Planning a synthetic claim is NOT evidence the caption or rights match.
    # A READY snapshot older than 90s is not even useful for a CAS rehearsal.
    if age > OBSERVE_MAX_AGE or age < timedelta(0):
        if any(str(x.get("status", "")).upper() == "READY" for x in queues):
            add("P0_REHEARSAL_OBSERVATION_NOT_FRESH")

    candidates: list[tuple[str, str, str]] = []
    if not problems:
        for row in queues:
            if str(row.get("status", "")).strip().upper() == "READY":
                candidates.append((
                    str(row["account_id"]).strip(), str(row["queue_id"]).strip(),
                    _digest({"row": row, "observed_at": observed.isoformat(),
                             "scope": "UNATTESTED_METADATA_ONLY"}),
                ))
    per_account = {}
    for account in sorted(KNOWN_ACCOUNTS):
        account_rows = [row for row in queues if row.get("account_id") == account]
        statuses = Counter(str(row.get("status", "")).strip().upper()
                           for row in account_rows)
        per_account[account] = {
            "queue_rows": len(account_rows),
            "ready_rows": statuses["READY"],
            "posted_rows": statuses["POSTED"],
            "unresolved_rows": sum(statuses[state] for state in TERMINAL_UNCERTAIN),
        }
    findings = [
        {"code": code, **({"identity_hash": h} if h else {})}
        for code, h in sorted(problems)
    ]
    report: dict[str, Any] = {
        "schema": REPORT_SCHEMA,
        "status": "CUTOVER_BLOCKED",
        "parity_status": "PASS_LOCAL_METADATA_ONLY" if not findings else "BLOCKED",
        "snapshot_sha256": _digest(snapshot),
        "queue_rows_count": len(queues),
        "posted_rows_count": len(posts),
        "per_account_counts": per_account,
        "candidate_count": len(candidates),
        "legacy_write_calls_remaining": legacy_writer_sites,
        "read_only_checks": True,
        "production_cutover_authorized": False,
        "publish_authorized": False,
        "sqlite_operational_write_authorized": False,
        "sheets_write_authorized": False,
        "provider_calls": 0,
        "source_provenance": "UNATTESTED_OFFLINE_METADATA_ONLY",
        "findings": findings,
        "mandatory_blockers": [
            "UNATTESTED_SOURCE_IDENTITY",
            "UNPROVEN_RUNTIME_WRITER_DISABLEMENT",
            "MISSING_LIVE_SINGLE_USE_POSTING_AUTHORITY",
            "MISSING_BACKUP_RESTORE_AND_OPERATOR_SIGNOFF",
            "MISSING_PROVIDER_CANARY_AND_DELIVERY_RECONCILIATION",
        ],
    }
    return Preflight(report, tuple(candidates), observed)


def simulate_to_rehearsal(plan: Preflight, *, ledger: object,
                          as_of: datetime) -> dict[str, Any]:
    """Only the exact non-authorizing P0QueueRehearsal type can be staged.

    Call ONLY with a fresh temporary database. Each stage internally commits;
    the caller is responsible for discarding the *entire* temporary DB on
    failure. No production database path is accepted by the CLI.
    """
    from p0_queue_cas_rehearsal import P0QueueRehearsal  # installed repo module

    if type(ledger) is not P0QueueRehearsal:
        raise P0PreflightBlocked("P0_NON_REHEARSAL_WRITER_REJECTED")
    if plan.report["parity_status"] != "PASS_LOCAL_METADATA_ONLY":
        raise P0PreflightBlocked("P0_REHEARSAL_BLOCKED_BY_FINDINGS")
    now = _now(as_of)
    if not timedelta(0) <= now - plan.observed_at <= OBSERVE_MAX_AGE:
        raise P0PreflightBlocked("P0_REHEARSAL_SOURCE_STALE")
    observed_count = 0
    for account, qid, source_hash in plan.candidates:
        operation_id = "p0_stage_" + _digest([account, qid, source_hash])[:32]
        result = ledger.observe(
            account_id=account, queue_id=qid, platform="threads",
            source_sha256=source_hash, observed_at=plan.observed_at,
            as_of=now, operation_id=operation_id,
        )
        if (result.get("status") != "OBSERVED_BLOCKED"
                or result.get("publish_authorized") is not False
                or result.get("sheets_write_allowed") is not False):
            raise P0PreflightBlocked("P0_REHEARSAL_RESULT_NOT_BLOCKED")
        observed_count += 1
    return {**plan.report, "simulated_observation_count": observed_count}
