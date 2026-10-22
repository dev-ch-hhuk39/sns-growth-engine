#!/usr/bin/env python3
"""Owner-only SNS release retention. No shared tool files or R2 mutation.

Runs from a root-owned immutable installed code copy. Every candidate must
pass the existing SNS seven-day, three-rollback, owner, mount and all-process
open-FD checks under the common VPS deploy lock. No network or Docker.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import prune_obsolete_runtime_releases as prune
import sns_storage_lifecycle_audit as audit

ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime")
PINNED_EMERGENCY_SHA = "bec16989c859e97abe53a736afb6d76bc12338a1"
MAX_RELEASES_PER_RUN = 2
MAX_BACKUP_AGE_SECONDS = 36 * 3600
BACKUP_UNITS = (
    "chadult-r2-offsite-backup.service",
    "chadult-r2-offsite-health.service",
)


class RetentionBlocked(RuntimeError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise RetentionBlocked(reason)


def manual_backup_gate(now_monotonic_us: int | None = None) -> None:
    """Recent centrally managed R2 backup and health must pass; never edit it."""
    require(sys.platform == "linux" and os.geteuid() == 0, "ROOT_LINUX_ONLY")
    now = int(time.monotonic() * 1_000_000) if now_monotonic_us is None else now_monotonic_us
    for unit in BACKUP_UNITS:
        p = subprocess.run(
            ["systemctl", "show", unit, "--no-pager",
             "-p", "Result", "-p", "ExecMainStatus",
             "-p", "ExecMainExitTimestampMonotonic"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, timeout=15, check=False,
        )
        require(p.returncode == 0, "R2_SERVICE_STATE_UNAVAILABLE")
        state = dict(line.split("=", 1) for line in p.stdout.splitlines() if "=" in line)
        require(state.get("Result") == "success" and state.get("ExecMainStatus") == "0",
                "R2_BACKUP_OR_HEALTH_FAILED")
        try:
            then = int(state["ExecMainExitTimestampMonotonic"])
        except (ValueError, KeyError):
            raise RetentionBlocked("R2_LAST_SUCCESS_TIME_UNVERIFIED") from None
        age = now - then
        require(0 <= age <= MAX_BACKUP_AGE_SECONDS * 1_000_000,
                "R2_BACKUP_OR_HEALTH_TOO_OLD")
    enabled = subprocess.run(
        ["systemctl", "is-enabled", "chadult-r2-offsite-backup.timer"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, timeout=10, check=False,
    )
    require(enabled.returncode == 0 and enabled.stdout.strip() == "enabled",
            "R2_BACKUP_TIMER_NOT_ENABLED")


def choose_targets(inventory: dict, *, pinned_sha: str = PINNED_EMERGENCY_SHA) -> list[str]:
    """Only auditor-labeled, exact-SHA, seven-day-aged releases are candidates."""
    expected = inventory.get("pointers", {}).get("current")
    require(bool(prune.SHA.fullmatch(str(expected))), "CURRENT_SHA_UNVERIFIED")
    keep = {s for s in inventory.get("pointers", {}).values() if s}
    keep.add(inventory.get("emergency_recovery_sha"))
    keep.add(pinned_sha)
    releases = inventory.get("releases")
    require(isinstance(releases, list) and 3 <= len(releases) <= 32,
            "SNS_RELEASE_INVENTORY_UNSAFE")
    seen: set[str] = set()
    choices: list[tuple[int, str]] = []
    for row in releases:
        sha = row.get("sha")
        require(type(sha) is str and prune.SHA.fullmatch(sha) is not None
                and sha not in seen, "SNS_RELEASE_IDENTITY_UNSAFE")
        seen.add(sha)
        if sha in keep:
            continue
        if row.get("protected_reason") != "CANDIDATE_REQUIRES_APPROVAL_AND_IN_USE_SCAN":
            continue
        require(row.get("marker_valid") is True and row.get("age_days", -1) >= 7,
                "SNS_RETENTION_AGE_OR_OWNER_INVALID")
        size = row.get("allocated_bytes")
        require(type(size) is int and 0 <= size <= 3 * 1024**3,
                "SNS_RETENTION_SIZE_INVALID")
        choices.append((size, sha))
    # Max two each day. Biggest reclaim first; stable SHA tie-breaker.
    choices.sort(key=lambda entry: (-entry[0], entry[1]))
    return [sha for _, sha in choices[:MAX_RELEASES_PER_RUN]]


def run(*, confirm: bool) -> dict:
    require(sys.platform == "linux" and os.geteuid() == 0, "ROOT_LINUX_ONLY")
    require(ROOT.is_dir() and not ROOT.is_symlink(), "SNS_RUNTIME_ROOT_INVALID")
    inventory = audit.audited_release_inventory(ROOT)
    pinned = ROOT / "releases" / PINNED_EMERGENCY_SHA
    if pinned.exists():
        require(prune.release_bootable(pinned), "PINNED_EMERGENCY_NOT_BOOTABLE")
    targets = choose_targets(inventory)
    report = {
        "status": "PASS", "mode": "APPLY" if confirm else "AUDIT",
        "scope": "sns_growth_immutable_releases_only",
        "age_floor_days": 7, "candidates": len(targets),
        "planned_reclaim_bytes": sum(
            x["allocated_bytes"] for x in inventory["releases"] if x["sha"] in targets
        ), "removed_count": 0, "freed_bytes": 0,
        "current_rollback_protected": True,
        "pinned_emergency_protected": True,
        "other_services_modified": False, "r2_modified": False,
    }
    if not confirm or not targets:
        return report
    # The destructive operation is impossible unless both centrally managed
    # offsite backup and health have succeeded recently and the timer is on.
    manual_backup_gate()
    expected = inventory["pointers"]["current"]
    # Revalidate SHA pointers, seven-day cutoff, owner/mount and process use
    # inside prune.run's shared global deployment lock before unlinking.
    result = prune.run(ROOT, expected, targets, confirm=True)
    report["removed_count"] = len(result["removed_releases"])
    report["freed_bytes"] = result["recovered_bytes"]
    report["status"] = result["status"]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        report = run(confirm=args.apply)
        print(json.dumps(report, sort_keys=True))
        return 0
    except (RetentionBlocked, audit.StorageAuditBlocked, RuntimeError,
            OSError, subprocess.TimeoutExpired):
        print(json.dumps({
            "status": "BLOCKED", "scope": "sns_growth_immutable_releases_only",
            "other_services_modified": False, "r2_modified": False,
            "deletion_success_not_claimed": True,
        }, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
