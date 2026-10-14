#!/usr/bin/env python3
"""One-command OFFLINE P0 release rehearsal, forever CUTOVER_BLOCKED.

Combines existing snapshot parser, frozen AST writer inventory, memory-only
shadow parity, and existing blocked SQLite CAS. No API credentials/transport.
This is NOT an operational cutover and must NEVER be used as a publish gate.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from p0_release_readiness import P0ReleaseBlocked, run_rehearsal

ROOT = Path(__file__).resolve().parents[1]


def report(args: argparse.Namespace) -> dict:
    if not args.simulate:
        raise P0ReleaseBlocked("P0_RELEASE_EXPLICIT_SIMULATE_REQUIRED")
    if (not args.before.is_absolute() or not args.after.is_absolute()
            or args.before.resolve() == args.after.resolve()):
        raise P0ReleaseBlocked("P0_RELEASE_TWO_DIFFERENT_ABSOLUTE_SNAPSHOTS_REQUIRED")
    # Follow no symlinks; two hardlinks to the same file are also not two
    # independent captures, even when distinct absolute filenames are used.
    if (args.before.is_symlink() or args.after.is_symlink()
            or args.before.stat().st_dev == args.after.stat().st_dev
            and args.before.stat().st_ino == args.after.stat().st_ino):
        raise P0ReleaseBlocked("P0_RELEASE_SOURCE_FILE_NOT_INDEPENDENT")

    # Lazy imports for the actual Mac checkout. The isolated package is not
    # evidence that the local Git baseline or provider identity was checked.
    from audit_queue_authority_cutover import load_offline_snapshot
    from plan_legacy_writer_cutover import build_plan
    from p0_queue_cas_rehearsal import P0QueueRehearsal  # noqa: F401

    plan = build_plan()  # AST inventory must match the frozen baseline.
    before = load_offline_snapshot(args.before)
    after = load_offline_snapshot(args.after)
    return run_rehearsal(
        before, after, as_of=datetime.now(timezone.utc),
        legacy_plan=plan,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--simulate", action="store_true")
    parser.add_argument("--output", type=Path,
                        help="Optional NEW sanitized report outside checkout")
    args = parser.parse_args()
    try:
        result = report(args)
    except Exception:
        # No exception text (provider credentials, file names or queue IDs)
        # may be copied into a report or stdout.
        result = {
            "schema": "sns_p0_release_readiness_offline_v1",
            "status": "CUTOVER_BLOCKED",
            "local_rehearsal_status": "NOT_PROVEN",
            "production_cutover_authorized": False,
            "publish_authorized": False,
            "external_write_count": 0, "provider_call_count": 0,
            "findings": ["P0_RELEASE_SOURCE_INVENTORY_OR_LOCAL_CAS_UNVERIFIABLE"],
        }
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        resolved = args.output.resolve()
        if (not args.output.is_absolute() or ROOT == resolved
                or ROOT in resolved.parents):
            parser.error("P0_RELEASE_REPORT_MUST_BE_OUTSIDE_CHECKOUT")
        flags = os.O_EXCL | os.O_CREAT | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(args.output, flags, 0o600)
        except OSError:
            parser.error("P0_RELEASE_REPORT_ALREADY_EXISTS_OR_UNAVAILABLE")
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(payload)
    print(payload, end="")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
