#!/usr/bin/env python3
"""Read-only, redacted diagnosis of one abandoned SNS pending release.

Does not remove symlinks, change configuration, start a publisher, deploy,
or read/print token values. Shared deployment lock is probed non-blocking.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
from pathlib import Path

from prune_obsolete_runtime_releases import assert_not_in_use
from resolve_abandoned_sns_pending import ROOT, LOCK, PendingBlocked, inspect

SHA = re.compile(r"[a-f0-9]{40}\Z")
PROCESS_CATEGORIES = {
    "process_cmdline_inventory_unknown": "PROCESS_INVENTORY_UNREADABLE",
    "process_cwd_inventory_unknown": "PROCESS_INVENTORY_UNREADABLE",
    "process_fd_inventory_unknown": "PROCESS_INVENTORY_UNREADABLE",
    "target_release_in_use": "PENDING_RELEASE_IN_USE",
    "target_release_open_fd": "PENDING_RELEASE_IN_USE",
    "linux_proc_required": "PROCESS_INVENTORY_UNREADABLE",
}


def exact_pointer(root: Path, name: str, expected: str) -> bool:
    p = root / name
    if not p.is_symlink() or SHA.fullmatch(expected) is None:
        return False
    try:
        target = p.resolve(strict=True)
        releases = (root / "releases").resolve(strict=True)
    except (OSError, RuntimeError):
        return False
    return (target.parent == releases and target.name == expected
            and target.is_dir() and not target.is_symlink())


def diagnose(current: str, previous: str, pending: str, *,
             root: Path = ROOT, lock: Path = LOCK) -> dict[str, str | bool]:
    base = {"would_post": False, "would_delete": False, "would_deploy": False}
    if not (SHA.fullmatch(current) and SHA.fullmatch(previous) and SHA.fullmatch(pending)):
        return {**base, "status": "BLOCKED", "category": "EXPECTED_SHA_INVALID"}
    if not (exact_pointer(root, "current", current)
            and exact_pointer(root, "previous", previous)):
        return {**base, "status": "BLOCKED", "category": "CURRENT_OR_ROLLBACK_MISMATCH"}
    link = root / "pending"
    if not link.exists() and not link.is_symlink():
        return {**base, "status": "ALREADY_ABSENT", "category": "NO_PENDING_LINK"}
    if not exact_pointer(root, "pending", pending):
        return {**base, "status": "BLOCKED", "category": "PENDING_IDENTITY_MISMATCH"}
    try:
        inspect(root, current, pending)
    except (PendingBlocked, OSError, RuntimeError):
        return {**base, "status": "BLOCKED", "category": "PRIVATE_RUNTIME_SAFETY_UNVERIFIED"}
    if not os.access(root, os.W_OK | os.X_OK):
        return {**base, "status": "BLOCKED", "category": "PENDING_PARENT_NOT_WRITABLE"}
    if not lock.is_file() or lock.is_symlink():
        return {**base, "status": "BLOCKED", "category": "SHARED_LOCK_UNAVAILABLE"}
    try:
        with lock.open("rb") as locked:
            try:
                fcntl.flock(locked.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return {**base, "status": "BLOCKED", "category": "SHARED_LOCK_BUSY_OR_DENIED"}
            try:
                if not exact_pointer(root, "pending", pending):
                    return {**base, "status": "BLOCKED", "category": "PENDING_CHANGED"}
                try:
                    assert_not_in_use([root / "releases" / pending])
                except RuntimeError as exc:
                    return {**base, "status": "BLOCKED", "category": PROCESS_CATEGORIES.get(
                        str(exc), "PROCESS_INVENTORY_UNVERIFIED")}
                except (OSError, PermissionError):
                    return {**base, "status": "BLOCKED", "category": "PROCESS_INVENTORY_UNREADABLE"}
            finally:
                fcntl.flock(locked.fileno(), fcntl.LOCK_UN)
    except OSError:
        return {**base, "status": "BLOCKED", "category": "SHARED_LOCK_UNAVAILABLE"}
    return {**base, "status": "SAFE_TO_EVALUATE_SEPARATE_REPAIR",
            "category": "READ_ONLY_PRECHECK_PASS"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-current", required=True)
    parser.add_argument("--expected-previous", required=True)
    parser.add_argument("--expected-pending", required=True)
    args = parser.parse_args()
    result = diagnose(args.expected_current, args.expected_previous, args.expected_pending)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
