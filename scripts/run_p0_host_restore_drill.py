#!/usr/bin/env python3
"""Read-only host wrapper: verify an existing private P0 ledger can be restored.

Parses owner-only runtime.env as data, never sources it as shell code.
Requires posting and P0 gate OFF plus a shared deployment lock.
Does not update the ledger, runtime.env, Sheets, posting settings, or backup.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import re
from pathlib import Path

from p0_ledger_backup_restore_drill import DrillBlocked, run_drill
from provision_p0_once_host_authority import (
    BootstrapBlocked, _parse_env, _validate_root,
)

CONFIRM = "READONLY_EPHEMERAL_P0_RESTORE"
HOST_ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime")
DEPLOY_LOCK = Path("/run/lock/chadult-production-deploy.lock")


def host_drill(
    runtime_root: Path,
    lock_file: Path,
    *,
    confirmation: str,
    allow_test_path: bool = False,
) -> dict:
    if confirmation != CONFIRM:
        raise DrillBlocked("P0_HOST_DRILL_EXPLICIT_CONFIRMATION_REQUIRED")
    if lock_file.is_symlink() or not lock_file.is_file():
        raise DrillBlocked("P0_HOST_DRILL_SHARED_DEPLOY_LOCK_UNAVAILABLE")
    try:
        shared, envfile = _validate_root(runtime_root)
        original_stat = envfile.stat()
        settings = dict(_parse_env(envfile))
        if (settings.get("BUFFERED_POSTING_ENABLED") != "false"
                or settings.get("SNS_P0_ONCE_GATE_ENABLED") != "false"):
            raise DrillBlocked("P0_HOST_DRILL_POSTING_MUST_REMAIN_OFF")
        expected_db = shared / "p0_once_private" / "once.sqlite3"
        if (settings.get("SNS_P0_ONCE_DB_PATH") != str(expected_db)
                or expected_db.is_symlink()):
            raise DrillBlocked("P0_HOST_DRILL_EXPECTED_LEDGER_MISMATCH")
        key = settings.get("SNS_P0_ONCE_HMAC_KEY_HEX", "")
        if not re.fullmatch(r"[a-fA-F0-9]{64}", key):
            raise DrillBlocked("P0_HOST_DRILL_KEY_MISSING")
        # Shared, non-blocking lock: do not contend with a deploy or bootstrap.
        with lock_file.open("rb") as lock:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
            except BlockingIOError:
                raise DrillBlocked("P0_HOST_DRILL_DEPLOYMENT_IN_PROGRESS") from None
            try:
                result = run_drill(
                    str(expected_db), bytes.fromhex(key),
                    allow_test_path=allow_test_path,
                )
            finally:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        after = envfile.stat()
        if ((original_stat.st_ino, original_stat.st_size, original_stat.st_mtime_ns)
                != (after.st_ino, after.st_size, after.st_mtime_ns)):
            raise DrillBlocked("P0_HOST_DRILL_RUNTIME_SETTINGS_CHANGED")
        result["host_runtime_settings_modified"] = False
        result["shared_deploy_lock_held_for_drill"] = True
        result["posting_still_disabled"] = True
        return result
    except DrillBlocked:
        raise
    except (BootstrapBlocked, OSError, ValueError, TypeError):
        raise DrillBlocked("P0_HOST_DRILL_RUNTIME_UNVERIFIABLE") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, default=HOST_ROOT)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    try:
        report = host_drill(args.runtime_root, DEPLOY_LOCK, confirmation=args.confirm)
    except DrillBlocked as exc:
        print(json.dumps({
            "status": "BLOCKED", "reason": str(exc),
            "publish_authorized": False, "production_cutover_authorized": False,
        }, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({
            "status": "BLOCKED", "reason": "P0_HOST_DRILL_UNVERIFIED",
            "publish_authorized": False, "production_cutover_authorized": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
