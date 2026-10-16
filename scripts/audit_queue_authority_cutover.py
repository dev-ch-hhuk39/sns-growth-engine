#!/usr/bin/env python3
"""Local, read-only audit for a FUTURE Sheets/SQLite authority cutover.

This tool never creates a DB, makes Google/SNS requests, writes operational
state, grants media READY, or authorizes a cutover. The operational manifest
must be prepared independently by Ops and is NEVER trusted as signed evidence.
No post text, media URL, queue ID or proof payload is emitted in reports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from media_managed_queue_writer import (  # noqa: E402
    _history as managed_history, _row as managed_row,
)
from media_shadow_queue_authority import (  # noqa: E402
    _history as shadow_history, _row as shadow_row,
)
from media_mirror_outbox import (  # noqa: E402
    _audit as outbox_history, _head as outbox_head,
    _projection_for as verify_mirror_projection,
)
from publishers.media_publish_interlock import (  # noqa: E402
    media_publish_authority_required,
)
from test_phase5b6h_legacy_sheets_mutation_inventory import (  # noqa: E402
    MANIFEST, collect_inventory,
)

SCHEMA = "sns_operational_queue_offline_metadata_v1"
ALLOWED_ACCOUNTS = frozenset(("night_scout", "liver_manager"))
ALLOWED_QUEUE_KEYS = frozenset((
    "queue_id", "account_id", "slot_id", "platform", "status",
    "media_required", "media_asset_id", "media_type", "publisher_media_type",
    "content_type", "generation_mode", "content_route", "has_media",
))
ALLOWED_POST_KEYS = frozenset((
    "queue_id", "account_id", "status", "real_post",
    "verification_status", "external_post_id",
))
VALID_STATUSES = frozenset((
    "WAITING_REVIEW", "READY", "PLANNED", "DRAFT", "REJECTED",
    "PROCESSING", "POSTED", "FAILED", "DUPLICATE_BLOCKED",
    "POSTED_SAVE_FAILED", "POSTED_SAVE_UNVERIFIED", "PUBLISH_OUTCOME_UNVERIFIED",
    "BLOCKED_INTERNAL_LEAK", "SAFETY_STOP_HYBRID_AI_GATE",
))
UNKNOWN_STATUSES = frozenset((
    "PROCESSING", "POSTED_SAVE_FAILED", "POSTED_SAVE_UNVERIFIED",
    "PUBLISH_OUTCOME_UNVERIFIED",
))
MAX_FILE_BYTES = 1048576
MAX_ROWS = 10000
MAX_SHEET_AGE = timedelta(minutes=5)
MAX_CLOCK_SKEW = timedelta(minutes=2)
MAX_SHADOW_AGE = timedelta(seconds=90)
ZERO = "0" * 64


class AuditBlocked(ValueError):
    """Only static reason codes; no raw operational source content."""


def _parse_iso(value: Any) -> datetime:
    if not isinstance(value, str):
        raise AuditBlocked("OFFLINE_SNAPSHOT_TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise AuditBlocked("OFFLINE_SNAPSHOT_TIMESTAMP_INVALID") from None
    if parsed.tzinfo is None:
        raise AuditBlocked("OFFLINE_SNAPSHOT_TIMESTAMP_INVALID")
    return parsed.astimezone(timezone.utc)


def _key(row: dict[str, Any]) -> tuple[str, str, str]:
    return tuple(str(row.get(name, "")).strip()
                 for name in ("account_id", "slot_id", "queue_id"))


def _ref(key: tuple[str, str, str]) -> str:
    return hashlib.sha256(json.dumps(
        key, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")).hexdigest()[:20]


def _problem(code: str, key: tuple[str, str, str] | None = None) -> dict[str, str]:
    result = {"code": code}
    if key is not None:
        result["identity_hash"] = _ref(key)
    return result


def load_offline_snapshot(path: Path) -> dict[str, Any]:
    """Strict minimal-metadata input. Forbid bodies, URLs, secrets and raw logs."""
    try:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            raise AuditBlocked("OFFLINE_SNAPSHOT_UNAVAILABLE_OR_OVERSIZED")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise AuditBlocked("OFFLINE_SNAPSHOT_UNAVAILABLE_OR_INVALID") from None
    if (not isinstance(value, dict)
            or set(value) != {"schema", "observed_at", "queue_rows", "posted_rows"}
            or value.get("schema") != SCHEMA):
        raise AuditBlocked("OFFLINE_SNAPSHOT_SCHEMA_INVALID")
    for collection, allowed in (("queue_rows", ALLOWED_QUEUE_KEYS),
                                ("posted_rows", ALLOWED_POST_KEYS)):
        rows = value[collection]
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            raise AuditBlocked("OFFLINE_SNAPSHOT_ROWS_INVALID")
        for row in rows:
            if (not isinstance(row, dict) or not set(row).issubset(allowed)
                    or any(not isinstance(v, (str, bool)) for v in row.values())):
                raise AuditBlocked("OFFLINE_SNAPSHOT_UNSAFE_FIELD")
    _parse_iso(value["observed_at"])
    return value


def inspect_protected_sqlite(db: sqlite3.Connection) -> dict[str, Any]:
    """Revalidate existing immutable event chains using existing source code.

    Does not import review evidence or make an authorization decision. SQLite
    input is opened mode=ro/query_only by the CLI. No migrations run.
    """
    required = (
        "sns_media_shadow_queue_heads", "sns_media_shadow_queue_events",
        "sns_media_managed_queue_heads", "sns_media_managed_queue_events",
        "sns_media_sheet_mirror_previews", "sns_media_mirror_outbox_heads",
        "sns_media_mirror_outbox_events",
    )
    try:
        present = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'",
        )}
        if not set(required).issubset(present):
            raise AuditBlocked("PROTECTED_DB_MIGRATIONS_0006_0008_MISSING")
        records = db.execute(
            """SELECT account_id,slot_id,queue_id FROM sns_media_managed_queue_heads
               ORDER BY account_id,slot_id,queue_id""",
        ).fetchall()
        if len(records) > MAX_ROWS:
            raise AuditBlocked("PROTECTED_DB_TOO_MANY_QUEUE_HEADS")
        result: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in records:
            key = tuple(row)
            if not all(isinstance(v, str) and v for v in key) or key in result:
                raise AuditBlocked("PROTECTED_DB_IDENTITY_INVALID")
            managed = managed_row(db, key)
            shadow = shadow_row(db, key)
            managed_history(db, key, managed)
            shadow_history(db, key, shadow)
            if not managed or not shadow:
                raise AuditBlocked("PROTECTED_DB_SHADOW_MISSING")
            if managed["queue_sha256"] != shadow["queue_sha256"]:
                raise AuditBlocked("PROTECTED_DB_QUEUE_HASH_CONFLICT")
            event_id = managed["last_event_sha256"]
            outbox = outbox_head(db, event_id)
            outbox_history(db, event_id, outbox)
            if not outbox or tuple(outbox[field] for field in (
                "account_id", "slot_id", "queue_id",
            )) != key:
                raise AuditBlocked("PROTECTED_DB_OUTBOX_MISSING")
            verify_mirror_projection(db, event_id, outbox)
            result[key] = {
                "managed_state": managed["state"],
                "shadow_state": shadow["state"],
                "outbox_state": outbox["state"],
                "updated_at": shadow["updated_at"],
            }
        # A mirror-only head without its managed counterpart is not a
        # publishable source and must be inspected manually before migration.
        dangling = db.execute(
            """SELECT COUNT(*) FROM sns_media_mirror_outbox_heads o
               LEFT JOIN sns_media_managed_queue_heads m
                 ON o.account_id=m.account_id AND o.slot_id=m.slot_id
                AND o.queue_id=m.queue_id
               WHERE m.queue_id IS NULL""",
        ).fetchone()[0]
        if dangling:
            raise AuditBlocked("PROTECTED_DB_DANGLING_OUTBOX")
        return {"status": "METADATA_CHAIN_CHECKED_LOCAL", "entries": result}
    except AuditBlocked:
        raise
    except Exception:
        raise AuditBlocked("PROTECTED_DB_INTEGRITY_UNVERIFIABLE") from None


def legacy_writer_snapshot() -> dict[str, Any]:
    """Reference the existing frozen AST inventory; never authorize it."""
    try:
        baseline = json.loads(MANIFEST.read_text(encoding="utf-8"))["routes"]
        current = collect_inventory()
    except Exception:
        raise AuditBlocked("LEGACY_WRITER_INVENTORY_UNAVAILABLE") from None
    if baseline != current:
        raise AuditBlocked("LEGACY_WRITER_INVENTORY_DRIFT")
    return {"files": len(current),
            "sites": sum(sum(count.values()) for count in current.values()),
            "source": "REVIEW_BASELINE_NOT_CUTOVER_AUTHORITY"}


def evaluate(
    snapshot: dict[str, Any], protected: dict[str, Any],
    inventory: dict[str, Any], *, now: datetime,
) -> dict[str, Any]:
    """Produce only count/hash/code evidence, never live production approval."""
    now = _parse_iso(now.isoformat())
    if (not isinstance(snapshot, dict) or snapshot.get("schema") != SCHEMA
            or not isinstance(snapshot.get("queue_rows"), list)
            or not isinstance(snapshot.get("posted_rows"), list)
            or protected.get("status") != "METADATA_CHAIN_CHECKED_LOCAL"
            or not isinstance(protected.get("entries"), dict)):
        raise AuditBlocked("AUDIT_INPUT_INVALID")
    findings: list[dict[str, str]] = []
    age = now - _parse_iso(snapshot.get("observed_at"))
    if age > MAX_SHEET_AGE or age < -MAX_CLOCK_SKEW:
        findings.append(_problem("OFFLINE_SNAPSHOT_NOT_FRESH"))
    row_identities: dict[str, list[dict[str, Any]]] = {}
    account_slots: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in snapshot["queue_rows"]:
        if not isinstance(row, dict):
            raise AuditBlocked("AUDIT_QUEUE_ROW_INVALID")
        key = _key(row)
        if not key[0] or not key[2]:
            findings.append(_problem("OPERATIONAL_QUEUE_IDENTITY_MISSING"))
            continue
        row_identities.setdefault(key[2], []).append(row)
        if key[0] not in ALLOWED_ACCOUNTS:
            findings.append(_problem("ACCOUNT_OUT_OF_CUTOVER_SCOPE", key))
        state = str(row.get("status", "")).upper()
        if state not in VALID_STATUSES:
            findings.append(_problem("OPERATIONAL_STATUS_INVALID", key))
        if state in UNKNOWN_STATUSES:
            findings.append(_problem("OPERATIONAL_OUTCOME_UNRESOLVED", key))
        media = media_publish_authority_required(
            account={"account_id": key[0]}, queue_item=row, derivative={},
            has_media=row.get("has_media") is True,
        )
        if media:
            if not key[1]:
                findings.append(_problem("MEDIA_SLOT_ID_MISSING", key))
            if key not in protected["entries"]:
                findings.append(_problem("PROTECTED_MEDIA_NOT_IN_SQLITE", key))
            if state in {"READY", "PROCESSING", "POSTED"}:
                findings.append(_problem("LEGACY_MEDIA_DELIVERY_NOT_AUTHORIZED", key))
        if key[1]:
            account_slots[key] = row
    for rows in row_identities.values():
        if len(rows) != 1:
            findings.append(_problem("GLOBAL_QUEUE_ID_COLLISION", _key(rows[0])))
    result_index: dict[str, list[dict[str, Any]]] = {}
    for posted in snapshot["posted_rows"]:
        if not isinstance(posted, dict):
            raise AuditBlocked("AUDIT_POSTED_ROW_INVALID")
        qid = str(posted.get("queue_id", ""))
        if not qid.strip() or not str(posted.get("account_id", "")).strip():
            findings.append(_problem("POSTED_RESULT_IDENTITY_MISSING"))
        result_index.setdefault(qid, []).append(posted)
        associated = row_identities.get(qid, [])
        if len(associated) == 1 and str(posted.get("account_id", "")) != str(
            associated[0].get("account_id", "")
        ):
            findings.append(_problem("POSTED_RESULT_CROSS_ACCOUNT_COLLISION", _key(associated[0])))
    for qid, rows in row_identities.items():
        if len(rows) != 1 or str(rows[0].get("status", "")).upper() != "POSTED":
            continue
        posted = result_index.get(qid, [])
        if not any(
            str(r.get("status", "")).upper() == "POSTED"
            and str(r.get("real_post", "")).lower() == "true"
            and str(r.get("verification_status", "")).upper() == "READ_AFTER_WRITE_PASS"
            and bool(str(r.get("external_post_id", "")).strip())
            and str(r.get("account_id", "")) == str(rows[0].get("account_id", ""))
            for r in posted
        ) or len(posted) != 1:
            findings.append(_problem("POSTED_RESULT_NOT_UNIQUELY_VERIFIED", _key(rows[0])))
    for key, state in protected["entries"].items():
        if key not in account_slots:
            findings.append(_problem("PROTECTED_ROW_ABSENT_FROM_OFFLINE_SHEETS", key))
        if (state["managed_state"] != "MANAGED_BLOCKED"
                or state["shadow_state"] != "SHADOW_BLOCKED"):
            findings.append(_problem("PROTECTED_QUEUE_NOT_ACTIVE_SNAPSHOT", key))
        if state["outbox_state"] in {"CLAIMED_BLOCKED", "UNCERTAIN_BLOCKED"}:
            findings.append(_problem("PROTECTED_MIRROR_OUTCOME_NOT_SETTLED", key))
        seen = _parse_iso(state["updated_at"])
        if now - seen > MAX_SHADOW_AGE or seen - now > MAX_CLOCK_SKEW:
            findings.append(_problem("PROTECTED_OBSERVATION_EXPIRED", key))
    sorted_findings = sorted(findings, key=lambda x: (x["code"], x.get("identity_hash", "")))
    return {
        "schema": "sns_queue_cutover_readonly_audit_v1",
        "status": "CUTOVER_BLOCKED",
        "local_parity_status": "PASS" if not sorted_findings else "BLOCKED",
        "production_cutover_authorized": False,
        "automatic_media_publish_authorized": False,
        "sqlite_writes": 0,
        "sheets_writes": 0,
        "sns_posts": 0,
        "source_provenance": "UNATTESTED_OFFLINE_METADATA_AND_LOCAL_SQLITE",
        "queue_rows": len(snapshot["queue_rows"]),
        "posted_rows": len(snapshot["posted_rows"]),
        "protected_heads": len(protected["entries"]),
        "legacy_writer_files": inventory["files"],
        "legacy_mutation_sites": inventory["sites"],
        "mandatory_activation_blockers": [
            "LEGACY_WRITERS_NOT_CUT_OVER",
            "OPERATIONAL_SOURCE_IDENTITY_NOT_ATTESTED",
            "PROTECTED_SQLITE_NOT_PUBLISH_AUTHORITY",
            "PROVIDER_PERMISSIONS_AND_CANARY_NOT_VERIFIED",
        ],
        "findings": sorted_findings,
    }


def open_readonly_db(path: Path) -> sqlite3.Connection:
    try:
        if not path.is_file():
            raise AuditBlocked("PROTECTED_DB_FILE_NOT_FOUND")
        encoded = quote(str(path.resolve()), safe="/")
        db = sqlite3.connect(f"file:{encoded}?mode=ro", uri=True,
                             isolation_level=None)
        db.execute("PRAGMA query_only=ON")
        return db
    except (sqlite3.Error, OSError):
        raise AuditBlocked("PROTECTED_DB_READONLY_OPEN_FAILED") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True,
                        help="Locally exported minimal metadata JSON; NO token/text/URLs")
    parser.add_argument("--protected-db", type=Path, required=True,
                        help="Existing protected SQLite DB, read-only")
    parser.add_argument("--output", type=Path,
                        help="Optional sanitized JSON report; no operational content")
    args = parser.parse_args()
    try:
        snapshot = load_offline_snapshot(args.snapshot)
        with closing(open_readonly_db(args.protected_db)) as db:
            protected = inspect_protected_sqlite(db)
        result = evaluate(snapshot, protected, legacy_writer_snapshot(),
                          now=datetime.now(timezone.utc))
    except AuditBlocked as exc:
        result = {"schema": "sns_queue_cutover_readonly_audit_v1",
                  "status": "CUTOVER_BLOCKED", "local_parity_status": "BLOCKED",
                  "production_cutover_authorized": False,
                  "reason": str(exc)}
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        if not args.output.is_absolute() or ROOT in args.output.resolve().parents:
            parser.error("sanitized_report_requires_external_absolute_path")
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    # A local comparison cannot authorize cutover, even if parity is clean.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
