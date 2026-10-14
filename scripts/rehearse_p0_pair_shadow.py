#!/usr/bin/env python3
"""Offline-only two-snapshot parity rehearsal with temporary memory SQLite.

Always exits 2/CUTOVER_BLOCKED. No --apply, live provider, shared DB, or
publishing capability. Emits only aggregate/hashes and fixed error codes.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from audit_queue_authority_cutover import (
    AuditBlocked, legacy_writer_snapshot, load_offline_snapshot,
)
from p0_pair_shadow_parity import (
    P0PairBlocked, compare_snapshots, initialize_ephemeral_shadow,
    stage_in_ephemeral_sqlite,
)
from p0_snapshot_cutover_preflight import P0PreflightBlocked

ROOT = Path(__file__).resolve().parents[1]


def report(args: argparse.Namespace) -> dict:
    if not args.simulate:
        raise P0PairBlocked("P0_PAIR_EXPLICIT_SIMULATE_REQUIRED")
    if (not args.before.is_absolute() or not args.after.is_absolute()
            or args.before.resolve() == args.after.resolve()):
        raise P0PairBlocked("P0_PAIR_TWO_SEPARATE_ABSOLUTE_EXPORTS_REQUIRED")
    inventory = legacy_writer_snapshot()  # existing frozen 6H AST baseline
    before = load_offline_snapshot(args.before)
    after = load_offline_snapshot(args.after)
    check = compare_snapshots(
        before, after, as_of=datetime.now(timezone.utc),
        legacy_writer_sites=inventory["sites"],
    )
    if check.report["pair_status"] != "PASS_LOCAL_METADATA_ONLY":
        return check.report
    with sqlite3.connect(":memory:", isolation_level=None) as db:
        db.execute("PRAGMA foreign_keys=ON")
        initialize_ephemeral_shadow(db, explicitly_for_tests=True)
        return stage_in_ephemeral_sqlite(
            check, db, as_of=datetime.now(timezone.utc),
            explicit_temporary_rehearsal=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True,
                        help="First minimal metadata-only export (offline)")
    parser.add_argument("--after", type=Path, required=True,
                        help="Second minimal metadata-only export (offline)")
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--output", type=Path,
                        help="Optional new sanitized JSON report outside repo")
    args = parser.parse_args()
    try:
        result = report(args)
    except (AuditBlocked, P0PairBlocked, P0PreflightBlocked,
            sqlite3.Error, OSError, ValueError, TypeError):
        result = {
            "schema": "sns_p0_two_snapshot_parity_v1",
            "status": "CUTOVER_BLOCKED", "pair_status": "BLOCKED",
            "reason": "P0_PAIR_INPUT_OR_SHADOW_UNVERIFIABLE",
            "production_cutover_authorized": False,
            "publish_authorized": False,
            "sheets_write_authorized": False,
            "operational_sqlite_write_authorized": False,
            "provider_calls": 0,
        }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        destination = args.output.resolve()
        if (not args.output.is_absolute() or destination == ROOT
                or ROOT in destination.parents):
            parser.error("P0_REPORT_MUST_BE_NEW_PATH_OUTSIDE_REPOSITORY")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(args.output, flags, 0o600)
        except OSError:
            parser.error("P0_REPORT_DESTINATION_UNAVAILABLE_OR_ALREADY_EXISTS")
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(text)
    print(text, end="")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
