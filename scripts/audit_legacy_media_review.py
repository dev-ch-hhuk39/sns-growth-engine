#!/usr/bin/env python3
"""Read-only inventory of media READY/approval surfaces requiring trust migration.

Input: an already captured Phase 5B-3 queue snapshot. Never fetches Sheets,
authenticates, changes READY, triggers posts or reports raw media/caption URLs.
An existing READY row is *not* evidence of authenticated approval.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any

from media_review_legacy_guard import (
    is_protected_media_candidate, requires_strict_review_block,
)

SOURCE_SCHEMA = "sns_media_queue_snapshot_v1"
REPORT_SCHEMA = "sns_legacy_media_approval_audit_v1"
SAFE_ID = re.compile(r"[A-Za-z0-9_.:-]{1,128}\Z")
MAX_ROWS = 200
STATUS_CODES = {
    "WAITING_REVIEW": "LEGACY_READY_PROMOTION_POSSIBLE",
    "READY": "EXISTING_READY_NEEDS_CANONICAL_RIGHTS_REVIEW",
    "POSTED": "POSTED_NEEDS_HISTORICAL_EVIDENCE_REVIEW",
}


class LegacyAuditBlocked(ValueError):
    pass


def build_legacy_media_audit(source: Any) -> dict[str, Any]:
    if (not isinstance(source, dict)
            or source.get("schema_version") != SOURCE_SCHEMA
            or source.get("read_only") is not True):
        raise LegacyAuditBlocked("invalid_readonly_snapshot")
    rows = source.get("rows")
    if (not isinstance(rows, list) or len(rows) > MAX_ROWS
            or any(not isinstance(row, dict) for row in rows)):
        raise LegacyAuditBlocked("invalid_snapshot_rows")
    if not isinstance(source.get("captured_at"), str) or not source["captured_at"]:
        raise LegacyAuditBlocked("missing_snapshot_time")

    identities: set[tuple[str, str]] = set()
    flagged: list[dict[str, Any]] = []
    ignored = 0
    for row in rows:
        account = row.get("account_id")
        queue_id = row.get("queue_id")
        if not isinstance(account, str) or not isinstance(queue_id, str):
            raise LegacyAuditBlocked("queue_identity_invalid")
        if not SAFE_ID.fullmatch(account) or not SAFE_ID.fullmatch(queue_id):
            raise LegacyAuditBlocked("queue_identity_invalid")
        identity = (account, queue_id)
        if identity in identities:
            raise LegacyAuditBlocked("duplicate_queue_identity")
        identities.add(identity)
        if not is_protected_media_candidate(row):
            ignored += 1
            continue
        slot_id = row.get("slot_id") or ""
        if not isinstance(slot_id, str) or (slot_id and not SAFE_ID.fullmatch(slot_id)):
            raise LegacyAuditBlocked("slot_identity_invalid")
        status = str(row.get("status") or "").strip().upper()
        if status not in STATUS_CODES:
            ignored += 1
            continue
        flagged.append({
            "account_id": account,
            "slot_id": slot_id,
            "queue_id": queue_id,
            "observed_status": status,
            "review_code": STATUS_CODES[status],
            "legacy_strict_mode_would_block_new_ready": requires_strict_review_block(
                row, desired_status="READY", strict_trusted_media_review=True,
            ),
            "editable_sheet_ok_is_not_identity_proof": True,
            "authenticated_approval_verified": False,
            "canonical_rights_verified": False,
            "publish_authorized": False,
        })
    flagged.sort(key=lambda x: (
        {"READY": 0, "WAITING_REVIEW": 1, "POSTED": 2}[x["observed_status"]],
        x["account_id"], x["slot_id"], x["queue_id"],
    ))
    status_count = Counter(row["observed_status"] for row in flagged)
    return {
        "schema_version": REPORT_SCHEMA,
        "status": "READ_ONLY_MIGRATION_AUDIT",
        "source_snapshot_time": source["captured_at"],
        "source_row_count": len(rows),
        "protected_media_rows": len(flagged),
        "other_rows": ignored,
        "counts": {status: status_count[status] for status in STATUS_CODES},
        "items": flagged,
        "audit_not_proof_of_approval": True,
        "authenticated_approval_verified": False,
        "ready_transitions_performed": False,
        "writes_performed": False,
        "publish_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-snapshot-json", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.queue_snapshot_json.stat().st_size > 2_000_000:
            raise LegacyAuditBlocked("input_too_large")
        document = json.loads(args.queue_snapshot_json.read_text(encoding="utf-8"))
        report = build_legacy_media_audit(document)
        payload = json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        fd = os.open(args.output_json, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, LegacyAuditBlocked):
        print("LEGACY_MEDIA_REVIEW_AUDIT_BLOCKED")
        return 2
    print(json.dumps({
        "status": "READ_ONLY_MIGRATION_AUDIT",
        "protected_media_rows": report["protected_media_rows"],
        "counts": report["counts"],
        "publish_authorized": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
