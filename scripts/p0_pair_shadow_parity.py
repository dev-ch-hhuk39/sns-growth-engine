#!/usr/bin/env python3
"""Offline P0 two-snapshot parity and in-memory, nonauthorizing shadow import.

NEVER migration permission: both source snapshots are unauthenticated exports.
No Google/SNS client is imported and no operational database can be accepted.
Only minimal metadata permitted by Phase 6AH is inspected; captions, tokens,
URLs and media bytes are not allowed. No public report contains row identifiers.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from p0_snapshot_cutover_preflight import (
    _canonical,
    _check_rows,
    _now,
    _timestamp,
    inspect,
)

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "scripts/fixtures/sql/p0_shadow_parity_memory_schema.sql"
PAIR_SCHEMA = "sns_p0_two_snapshot_parity_v1"
SHADOW_SCHEMA = "sns_p0_shadow_parity_v1"
MAX_PAIR_GAP = timedelta(seconds=45)
MAX_SOURCE_AGE = timedelta(seconds=90)
ALLOWED = frozenset({"night_scout", "liver_manager"})
NO_AUTHORITY = {
    "status": "CUTOVER_BLOCKED",
    "production_cutover_authorized": False,
    "publish_authorized": False,
    "sheets_write_authorized": False,
    "operational_sqlite_write_authorized": False,
    "provider_calls": 0,
    "source_provenance": "UNATTESTED_OFFLINE_METADATA_ONLY",
}


class P0PairBlocked(ValueError):
    """Only constant reason codes; no original text or row IDs in errors."""


def _sha(data: Any) -> str:
    return hashlib.sha256(_canonical(data).encode("ascii")).hexdigest()


def _hmac(key: bytes, value: Any) -> str:
    return hmac.new(key, _canonical(value).encode("ascii"), hashlib.sha256).hexdigest()


def _row_table(rows: list[dict], *, table: str) -> dict[str, dict]:
    """Internal-only index; IDs are intentionally absent from public reports."""
    indexed = {}
    for row in rows:
        queue_id = str(row.get("queue_id", "")).strip()
        if not queue_id or queue_id in indexed:
            raise P0PairBlocked("P0_PAIR_DUPLICATE_OR_MISSING_ROW_ID")
        indexed[queue_id] = row
    return indexed


@dataclass(frozen=True)
class PairCheck:
    report: dict[str, Any]
    # Do not serialize these fields; they contain offline private metadata.
    before_queue: tuple[dict, ...]
    before_posted: tuple[dict, ...]
    after_queue: tuple[dict, ...]
    after_posted: tuple[dict, ...]
    checked_at: datetime
    last_observed_at: datetime
    internal_evidence_sha256: str


def compare_snapshots(
    before: dict, after: dict, *, as_of: datetime,
    legacy_writer_sites: int,
) -> PairCheck:
    """Require two distinct, close-in-time, unchanged minimal-metadata views.

    Even a PASS_LOCAL_METADATA_ONLY cannot prove the source was fully exported,
    provider-authenticated, or free of external concurrent writers.
    """
    now = _now(as_of)
    pre = inspect(before, as_of=now, legacy_writer_sites=legacy_writer_sites)
    post = inspect(after, as_of=now, legacy_writer_sites=legacy_writer_sites)
    before_queues, before_posts = _check_rows(before)
    after_queues, after_posts = _check_rows(after)
    older = _timestamp(before["observed_at"])
    newer = _timestamp(after["observed_at"])
    reasons: set[str] = set()
    if pre.report["findings"] or post.report["findings"]:
        reasons.add("P0_SOURCE_PREFLIGHT_HAS_FINDINGS")
    if not timedelta(0) < newer - older <= MAX_PAIR_GAP:
        reasons.add("P0_PAIR_CAPTURE_INTERVAL_INVALID")
    if not timedelta(0) <= now - newer <= MAX_SOURCE_AGE:
        reasons.add("P0_PAIR_LATEST_CAPTURE_EXPIRED")
    if not timedelta(0) <= now - older <= MAX_SOURCE_AGE:
        reasons.add("P0_PAIR_FIRST_CAPTURE_EXPIRED")
    if not before_queues:
        reasons.add("P0_PAIR_EMPTY_QUEUE_NOT_PROOF")
    # A clean comparison is evidence of local metadata stability, NOT of a
    # complete provider export. Order within snapshots has no meaning.
    bq = _row_table(before_queues, table="queue")
    aq = _row_table(after_queues, table="queue")
    bp = _row_table(before_posts, table="post")
    ap = _row_table(after_posts, table="post")
    missing_queue = set(bq) - set(aq)
    new_queue = set(aq) - set(bq)
    missing_post = set(bp) - set(ap)
    new_post = set(ap) - set(bp)
    changed_queue = sum(
        bq[ident] != aq[ident] for ident in bq.keys() & aq.keys()
    )
    changed_post = sum(
        bp[ident] != ap[ident] for ident in bp.keys() & ap.keys()
    )
    if missing_queue or new_queue or missing_post or new_post:
        reasons.add("P0_PAIR_IDENTITY_SET_CHANGED")
    if changed_queue or changed_post:
        reasons.add("P0_PAIR_ROW_METADATA_CHANGED")

    pre_codes = {item["code"] for item in pre.report["findings"]}
    post_codes = {item["code"] for item in post.report["findings"]}
    # More precise, still sanitized finding codes, not any raw source values.
    reasons.update(pre_codes | post_codes)
    summary = {}
    for account in sorted(ALLOWED | {"beauty_account"}):
        summary[account] = {
            "before_queue": sum(x.get("account_id") == account for x in before_queues),
            "after_queue": sum(x.get("account_id") == account for x in after_queues),
            "before_posted": sum(x.get("account_id") == account for x in before_posts),
            "after_posted": sum(x.get("account_id") == account for x in after_posts),
        }
    report = {
        **NO_AUTHORITY,
        "schema": PAIR_SCHEMA,
        "pair_status": "BLOCKED" if reasons else "PASS_LOCAL_METADATA_ONLY",
        "queue_rows": len(before_queues),
        "posted_rows": len(before_posts),
        "queue_added": len(new_queue),
        "queue_missing": len(missing_queue),
        "queue_changed": changed_queue,
        "posted_added": len(new_post),
        "posted_missing": len(missing_post),
        "posted_changed": changed_post,
        "account_counts": summary,
        "legacy_write_calls_remaining": legacy_writer_sites,
        "export_completeness_attested": False,
        "provider_identity_verified": False,
        "runtime_writers_stopped": False,
        "independent_export_credential_verified": False,
        "findings": sorted(reasons),
        "mandatory_blockers": [
            "SOURCE_EXPORT_COMPLETENESS_UNATTESTED",
            "GOOGLE_PRINCIPAL_AND_ACL_UNVERIFIED",
            "EXTERNAL_AND_LEGACY_WRITERS_NOT_DISABLED",
            "PRODUCTION_CAS_AND_ROLLBACK_UNVERIFIED",
            "POST_AND_MEDIA_RIGHTS_PROVIDER_CANARY_MISSING",
        ],
    }
    # Freeze a private copy independent of the mutable source arguments.
    snapshots = (
        tuple(copy.deepcopy(before_queues)), tuple(copy.deepcopy(before_posts)),
        tuple(copy.deepcopy(after_queues)), tuple(copy.deepcopy(after_posts)),
    )
    evidence = _sha({
        "rows": [[_canonical(item) for item in group] for group in snapshots],
        "report_pair_status": report["pair_status"],
    })
    return PairCheck(
        report=report,
        before_queue=snapshots[0], before_posted=snapshots[1],
        after_queue=snapshots[2], after_posted=snapshots[3],
        checked_at=now, last_observed_at=newer,
        internal_evidence_sha256=evidence,
    )


def _ensure_memdb(db: sqlite3.Connection, *, initial: bool = False) -> None:
    if type(db) is not sqlite3.Connection or db.in_transaction:
        raise P0PairBlocked("P0_SHADOW_TEMPORARY_DATABASE_REQUIRED")
    try:
        entries = db.execute("PRAGMA database_list").fetchall()
        # Memory main database has a blank file path; reject all ATTACH uses.
        if len(entries) != 1 or entries[0][1] != "main" or entries[0][2] != "":
            raise P0PairBlocked("P0_SHADOW_TEMPORARY_DATABASE_REQUIRED")
        if db.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise P0PairBlocked("P0_SHADOW_FOREIGN_KEYS_REQUIRED")
        if db.execute("PRAGMA query_only").fetchone()[0] != 0:
            raise P0PairBlocked("P0_SHADOW_QUERY_ONLY_CONNECTION")
        existing = {
            x[0] for x in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'",
            )
        }
        required = {
            "sns_p0_shadow_batch", "sns_p0_shadow_queue", "sns_p0_shadow_post",
        }
        if initial and existing & required:
            raise P0PairBlocked("P0_SHADOW_SCHEMA_ALREADY_PRESENT")
        if not initial and not required.issubset(existing):
            raise P0PairBlocked("P0_SHADOW_SCHEMA_UNAVAILABLE")
    except sqlite3.Error:
        raise P0PairBlocked("P0_SHADOW_DATABASE_UNAVAILABLE") from None


def initialize_ephemeral_shadow(db: sqlite3.Connection, *, explicitly_for_tests: bool = False) -> None:
    if not explicitly_for_tests:
        raise P0PairBlocked("P0_SHADOW_EXPLICIT_TEST_FLAG_REQUIRED")
    _ensure_memdb(db, initial=True)
    try:
        db.executescript(MIGRATION.read_text(encoding="utf-8"))
        _ensure_memdb(db)
    except (sqlite3.Error, OSError):
        raise P0PairBlocked("P0_SHADOW_SCHEMA_INIT_FAILED") from None


def _rows_for_db(
    check: PairCheck, key: bytes, *, after: bool,
) -> tuple[list[tuple], list[tuple]]:
    queues = check.after_queue if after else check.before_queue
    posts = check.after_posted if after else check.before_posted
    qrows = [(
        _hmac(key, ["q", row["queue_id"]]),
        _hmac(key, ["qrecord", row]),
        str(row["account_id"]), str(row["status"]).upper(),
    ) for row in queues]
    prows = [(
        _hmac(key, ["p", row["queue_id"]]),
        _hmac(key, ["precord", row]),
        str(row["account_id"]), str(row["status"]).upper(),
    ) for row in posts]
    return sorted(qrows), sorted(prows)


def _manifest(queues: list[tuple], posts: list[tuple]) -> str:
    return _sha({"queue": queues, "post": posts})


def _fetch_staged(db: sqlite3.Connection, batch_id: str) -> tuple[list[tuple], list[tuple]]:
    return (
        db.execute(
            """SELECT identity_hmac,row_hmac,account_id,status
               FROM sns_p0_shadow_queue WHERE batch_id=? ORDER BY identity_hmac""",
            (batch_id,),
        ).fetchall(),
        db.execute(
            """SELECT identity_hmac,row_hmac,account_id,status
               FROM sns_p0_shadow_post WHERE batch_id=? ORDER BY identity_hmac""",
            (batch_id,),
        ).fetchall(),
    )


def stage_in_ephemeral_sqlite(
    check: PairCheck, db: sqlite3.Connection,
    *, as_of: datetime, explicit_temporary_rehearsal: bool = False,
    test_failpoint: str | None = None,
) -> dict[str, Any]:
    """Atomically stage a stable pair in :memory: only, then verify after.

    No returned flag, table or method conveys a publish/source cutover right.
    Caller must discard this SQLite connection after report verification.
    """
    if not explicit_temporary_rehearsal:
        raise P0PairBlocked("P0_SHADOW_EXPLICIT_REHEARSAL_REQUIRED")
    if type(check) is not PairCheck or check.report.get("pair_status") != "PASS_LOCAL_METADATA_ONLY":
        raise P0PairBlocked("P0_SHADOW_PAIR_NOT_STABLE")
    # Neither caller edits to mutable result fields nor in-place edits of
    # captured row dictionaries may upgrade an old P0 decision.
    recomputed_evidence = _sha({
        "rows": [[_canonical(item) for item in group] for group in (
            check.before_queue, check.before_posted,
            check.after_queue, check.after_posted,
        )],
        "report_pair_status": check.report["pair_status"],
    })
    if recomputed_evidence != check.internal_evidence_sha256:
        raise P0PairBlocked("P0_SHADOW_PREFLIGHT_EVIDENCE_CHANGED")
    now = _now(as_of)
    # Pair evidence cannot be cached and then imported much later as fresh.
    if (not timedelta(0) <= now - check.checked_at <= timedelta(seconds=15)
            or not timedelta(0) <= now - check.last_observed_at <= MAX_SOURCE_AGE):
        raise P0PairBlocked("P0_SHADOW_PRECHECK_EXPIRED")
    _ensure_memdb(db)
    key = secrets.token_bytes(32)
    before_queue, before_posts = _rows_for_db(check, key, after=False)
    after_queue, after_posts = _rows_for_db(check, key, after=True)
    if (before_queue != after_queue or before_posts != after_posts
            or not before_queue):
        raise P0PairBlocked("P0_SHADOW_PARITY_CHANGED_DURING_STAGING")
    batch_id = _hmac(key, ["batch", _manifest(before_queue, before_posts)])
    manifest = _manifest(before_queue, before_posts)
    # An in-memory DB contains only HMAC identifiers and metadata status,
    # never cleartext queue IDs, captions, post URLs, tokens or media bytes.
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            """INSERT INTO sns_p0_shadow_batch
               (batch_id,schema_version,queue_count,posted_count,
                source_fingerprint,row_manifest_hash,disposition)
               VALUES(?,?,?,?,?,?,?)""",
            (batch_id, SHADOW_SCHEMA, len(before_queue), len(before_posts),
             _sha({"source": "offline_unattested", "manifest": manifest}),
             manifest, "STAGED_BLOCKED"),
        )
        for identity, row_hash, account, status in before_queue:
            db.execute(
                """INSERT INTO sns_p0_shadow_queue
                   (batch_id,identity_hmac,row_hmac,account_id,status)
                   VALUES(?,?,?,?,?)""",
                (batch_id, identity, row_hash, account, status),
            )
        for identity, row_hash, account, status in before_posts:
            db.execute(
                """INSERT INTO sns_p0_shadow_post
                   (batch_id,identity_hmac,row_hmac,account_id,status)
                   VALUES(?,?,?,?,?)""",
                (batch_id, identity, row_hash, account, status),
            )
        if test_failpoint == "BEFORE_COMMIT":
            raise P0PairBlocked("P0_SHADOW_INJECTED_TEST_FAILURE")
        db.execute("COMMIT")
    except P0PairBlocked:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise
    except sqlite3.Error:
        if db.in_transaction:
            db.execute("ROLLBACK")
        raise P0PairBlocked("P0_SHADOW_SQLITE_OUTCOME_UNKNOWN_NO_REPLAY") from None
    # Compare both snapshots to the independently re-read staged rows.
    try:
        staged_queue, staged_posts = _fetch_staged(db, batch_id)
        head = db.execute(
            """SELECT schema_version,queue_count,posted_count,
                      row_manifest_hash,disposition
               FROM sns_p0_shadow_batch WHERE batch_id=?""",
            (batch_id,),
        ).fetchone()
    except sqlite3.Error:
        raise P0PairBlocked("P0_SHADOW_READBACK_FAILED_NO_REPLAY") from None
    if (staged_queue != after_queue or staged_posts != after_posts
            or head != (SHADOW_SCHEMA, len(after_queue), len(after_posts),
                        manifest, "STAGED_BLOCKED")
            or _manifest(staged_queue, staged_posts) != manifest):
        raise P0PairBlocked("P0_SHADOW_READBACK_MISMATCH_NO_REPLAY")
    return {
        **check.report,
        "shadow_status": "VERIFIED_TEMPORARY_METADATA_ONLY",
        "temporary_shadow_queue_rows": len(staged_queue),
        "temporary_shadow_posted_rows": len(staged_posts),
        "shadow_manifest_verified": True,
        "shadow_storage": "SQLITE_MEMORY_ONLY",
        "operational_db_writes": 0,
        "production_cutover_authorized": False,
        "publish_authorized": False,
    }


def authorize_posting(*_args: Any, **_kwargs: Any) -> None:
    raise P0PairBlocked("P0_SHADOW_NEVER_PUBLISH_AUTHORITY")
