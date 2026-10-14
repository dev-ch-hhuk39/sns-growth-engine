#!/usr/bin/env python3
"""Read-only P0 migration metadata check plus temporary blocked SQLite demo.

Expected exit code: 2 (CUTOVER_BLOCKED), including a passing rehearsal.
No --apply, persistent SQLite destination, provider login or SNS call exists.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from audit_queue_authority_cutover import (  # existing project parser
    AuditBlocked, legacy_writer_snapshot, load_offline_snapshot,
)
from p0_queue_cas_rehearsal import (  # existing isolated SQLite rehearsal
    P0QueueRehearsal, P0RehearsalBlocked, initialize_rehearsal_schema,
)
from p0_snapshot_cutover_preflight import (  # new pure planner
    P0PreflightBlocked, inspect, simulate_to_rehearsal,
)

ROOT = Path(__file__).resolve().parents[1]


def report(args: argparse.Namespace) -> dict:
    if not args.simulate:
        raise P0PreflightBlocked("P0_EXPLICIT_SIMULATE_REQUIRED")
    snapshot = load_offline_snapshot(args.snapshot)
    inventory = legacy_writer_snapshot()  # strict frozen AST baseline
    now = datetime.now(timezone.utc)
    plan = inspect(snapshot, as_of=now, legacy_writer_sites=inventory["sites"])
    if plan.report["parity_status"] != "PASS_LOCAL_METADATA_ONLY":
        return plan.report
    with tempfile.TemporaryDirectory(prefix="sns_p0_temp_batch_") as root:
        target = Path(root) / "rehearsal.sqlite3"
        db = sqlite3.connect(target, isolation_level=None, timeout=3)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            initialize_rehearsal_schema(db, explicit_local_test_only=True)
            return simulate_to_rehearsal(
                plan, ledger=P0QueueRehearsal(db), as_of=now,
            )
        finally:
            db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--output", type=Path,
                        help="Optional sanitized report; must not already exist")
    args = parser.parse_args()
    try:
        result = report(args)
    except (P0PreflightBlocked, P0RehearsalBlocked, AuditBlocked, sqlite3.Error):
        result = {
            "schema": "sns_p0_snapshot_preflight_v1",
            "status": "CUTOVER_BLOCKED", "parity_status": "BLOCKED",
            "publish_authorized": False, "sheets_write_authorized": False,
            "provider_calls": 0,
            "reason": "P0_SOURCE_OR_REHEARSAL_UNVERIFIABLE",
        }
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        destination = args.output.resolve()
        if (not args.output.is_absolute() or destination == ROOT
                or ROOT in destination.parents):
            parser.error("P0_REPORT_MUST_BE_OUTSIDE_REPOSITORY")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(destination, flags, 0o600)
        except OSError:
            parser.error("P0_REPORT_PATH_UNAVAILABLE_OR_ALREADY_EXISTS")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
    print(payload, end="")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
