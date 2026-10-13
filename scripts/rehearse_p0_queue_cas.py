#!/usr/bin/env python3
"""Offline only: exercise P0 SQLite one-use CAS; always CUTOVER_BLOCKED."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from p0_queue_cas_rehearsal import (  # noqa: E402
    P0QueueRehearsal, P0RehearsalBlocked, initialize_rehearsal_schema,
)
from plan_legacy_writer_cutover import build_plan  # noqa: E402


def demo() -> dict:
    # Do not treat an isolated CAS demonstration as migration completion.
    # Re-check the frozen AST baseline on every invocation and retain every
    # remaining legacy writer as a concrete operational release blocker.
    legacy = build_plan()
    remaining_p0 = sum(
        count for group, count in legacy["workstream_counts"].items()
        if group.startswith("P0_")
    )
    # No caller-supplied database, Sheets session, tokens or post content.
    now = datetime.now(timezone.utc)
    with tempfile.TemporaryDirectory(prefix="sns_p0_rehearsal_") as folder:
        db = sqlite3.connect(str(Path(folder) / "simulation.sqlite3"),
                             isolation_level=None, timeout=3)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            initialize_rehearsal_schema(db, explicit_local_test_only=True)
            ledger = P0QueueRehearsal(db)
            observed = ledger.observe(
                account_id="night_scout", queue_id="synthetic_p0_candidate",
                platform="threads", source_sha256="a" * 64,
                observed_at=now, as_of=now,
                operation_id="p0_observe_20261013_local_001",
            )
            claimed = ledger.claim(
                account_id="night_scout", queue_id="synthetic_p0_candidate",
                expected_revision=observed["revision"],
                expected_head_sha256=observed["head_sha256"],
                expected_source_sha256="a" * 64,
                as_of=now, operation_id="p0_claim_20261013_local_001",
            )
            unknown = ledger.quarantine(
                account_id="night_scout", queue_id="synthetic_p0_candidate",
                expected_revision=claimed["revision"],
                expected_head_sha256=claimed["head_sha256"],
                reason="ACK_UNKNOWN", as_of=now,
                operation_id="p0_uncertain_20261013_local_001",
            )
            replay_blocked = False
            try:
                ledger.claim(
                    account_id="night_scout", queue_id="synthetic_p0_candidate",
                    expected_revision=unknown["revision"],
                    expected_head_sha256=unknown["head_sha256"],
                    expected_source_sha256="a" * 64,
                    as_of=now, operation_id="p0_claim_retry_20261013_local_001",
                )
            except P0RehearsalBlocked:
                replay_blocked = True
            if not replay_blocked:
                raise P0RehearsalBlocked("P0_REPLAY_UNEXPECTED")
            return {
                "schema": "sns_p0_queue_cas_offline_report_v1",
                "status": "CUTOVER_BLOCKED",
                "stages": [observed["status"], claimed["status"], unknown["status"]],
                "replay_blocked": replay_blocked,
                "identity_hash": unknown["identity_hash"],
                "publish_authorized": False,
                "sheets_write_allowed": False,
                "operational_source_selected": False,
                "legacy_inventory_status": legacy["status"],
                "remaining_legacy_p0_write_calls": remaining_p0,
                "remaining_legacy_total_write_calls": legacy["not_migrated_sites"],
                "provider_api_calls": 0,
                "production_data_copied": False,
                "remaining_requirements": [
                    "OWNER_SIGNED_AUTHORITY_CUTOVER",
                    "PROVIDER_SERVICE_IDENTITY_AND_ACL",
                    "LEGACY_WRITERS_DISABLEMENT",
                    "ACTUAL_SHEETS_SNAPSHOT_AND_BACKUP_RESTORE",
                    "CROSS_PROCESS_PUBLISH_SINK_WIRING",
                    "PRODUCTION_CANARY_AND_REAL_READBACK",
                ],
            }
        finally:
            db.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true",
                        help="Only run temporary synthetic SQLite rehearsal")
    parser.add_argument("--output", type=Path,
                        help="Optional absolute JSON path outside repository")
    args = parser.parse_args()
    if not args.demo:
        parser.error("P0_OFFLINE_DEMO_EXPLICIT_FLAG_REQUIRED")
    report = demo()
    if args.output:
        if (not args.output.is_absolute()
                or ROOT == args.output.resolve()
                or ROOT in args.output.resolve().parents):
            parser.error("P0_REPORT_MUST_BE_EXTERNAL_ABSOLUTE_PATH")
        # Never overwrite an existing report or follow a malicious symlink.
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(args.output, flags, 0o600)
        except OSError:
            parser.error("P0_REPORT_PATH_ALREADY_EXISTS_OR_UNAVAILABLE")
        with os.fdopen(fd, "w", encoding="utf-8") as output_file:
            output_file.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))
    return 2  # a PASSING rehearsal never authorizes a production cutover


if __name__ == "__main__":
    raise SystemExit(main())
