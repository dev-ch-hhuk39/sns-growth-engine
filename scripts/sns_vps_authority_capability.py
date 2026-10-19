#!/usr/bin/env python3
"""Read-only resource and privilege inventory for the SNS VPS runner.

This program never elevates to root, writes state, opens secrets, removes
anything, or posts. sudo -n -l only queries permissions.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
from typing import Any

ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime")
RESOURCE_HELPER = "/usr/local/sbin/chadult-vps-resource-check"
GLOBAL_LOCK = Path("/run/lock/chadult-production-deploy.lock")
RELEASE_SHA = re.compile(r"[a-f0-9]{40}\Z")
MIN_AGE_SECONDS = 7 * 86400
STAGE_HEADROOM_BYTES = 9 * 1024 ** 3
CATEGORIES = {
    "process_cmdline_inventory_unknown": "PROCESS_CANNOT_PROVE_UNUSED",
    "process_cwd_inventory_unknown": "PROCESS_CANNOT_PROVE_UNUSED",
    "process_fd_inventory_unknown": "PROCESS_CANNOT_PROVE_UNUSED",
    "target_release_in_use": "PENDING_RELEASE_IN_USE",
    "target_release_open_fd": "PENDING_RELEASE_IN_USE",
    "linux_proc_required": "PROC_UNAVAILABLE",
}


def sudo_capability(*args: str) -> bool:
    """No output from sudo is returned; -l only checks permission."""
    if shutil.which("sudo") is None:
        return False
    try:
        done = subprocess.run(["sudo", "-n", "-l", *args], capture_output=True, check=False, timeout=6)
        return done.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def exact_pointer(root: Path, kind: str) -> str:
    point = root / kind
    if not point.is_symlink():
        return "MISSING_OR_UNSAFE"
    try:
        target = point.resolve(strict=True)
        releases = (root / "releases").resolve(strict=True)
        if (target.parent == releases and target.is_dir()
                and not target.is_symlink() and RELEASE_SHA.fullmatch(target.name)):
            return target.name
    except (OSError, RuntimeError):
        pass
    return "INVALID"


def age_eligible_candidates(root: Path, now: float) -> tuple[int, list[str]]:
    """Age eligibility is NOT permission to delete; process checks still required."""
    releases = root / "releases"
    if not releases.is_dir() or releases.is_symlink():
        return 0, []
    protected = {exact_pointer(root, k) for k in ("current", "previous", "pending")}
    eligible: list[str] = []
    count = 0
    try:
        entries = list(releases.iterdir())
    except OSError:
        return 0, []
    if len(entries) > 100:
        return 0, []
    for folder in entries:
        try:
            if folder.is_symlink() or not folder.is_dir() or not RELEASE_SHA.fullmatch(folder.name):
                continue
            if folder.name in protected:
                continue
            marker = folder / ".production-release"
            if not marker.is_file() or marker.is_symlink():
                continue
            if marker.stat().st_size > 128 or marker.read_text(encoding="ascii").strip() != folder.name:
                continue
            if now - folder.stat().st_mtime < MIN_AGE_SECONDS:
                continue
            count += 1
            eligible.append(folder.name)
        except (OSError, ValueError, UnicodeError):
            continue
    return count, sorted(eligible)[:5]


def process_eligibility(root: Path) -> str:
    pending = exact_pointer(root, "pending")
    if not RELEASE_SHA.fullmatch(pending):
        return "NO_VERIFIABLE_PENDING"
    try:
        from prune_obsolete_runtime_releases import assert_not_in_use
        assert_not_in_use([root / "releases" / pending])
        return "PROCESS_REFERENCE_PROOF_PASS"
    except Exception as exc:
        return CATEGORIES.get(str(exc), "PROCESS_INSPECTION_UNVERIFIED")


def report(root: Path = ROOT, *, now: float | None = None) -> dict[str, Any]:
    when = time.time() if now is None else now
    usage = shutil.disk_usage("/")
    count, age_candidates = age_eligible_candidates(root, when)
    pointers = {key: exact_pointer(root, key) for key in ("current", "previous", "pending")}
    return {
        "status": "READ_ONLY_COMPLETE",
        "runner_uid": os.geteuid(),
        "root_free_bytes": usage.free,
        "needs_for_9gib_bytes": max(0, STAGE_HEADROOM_BYTES - usage.free),
        "release_pointers": pointers,
        "pending_parent_writable": os.access(root, os.W_OK | os.X_OK),
        "shared_deploy_lock_accessible": (GLOBAL_LOCK.is_file() and not GLOBAL_LOCK.is_symlink()
                                          and os.access(GLOBAL_LOCK, os.R_OK | os.W_OK)),
        "sudo_resource_helper_list_permission": sudo_capability(RESOURCE_HELPER, "--preflight", "9"),
        "sudo_root_process_observer_list_permission": sudo_capability(
            "/usr/bin/python3", "-B", "/usr/local/sbin/chadult-sns-process-inspect", "--readonly"
        ),
        "age_only_releases_count": count,
        "age_only_release_ids": age_candidates,
        "age_only_never_proves_unused": True,
        "pending_process_usage_proof": process_eligibility(root),
        "post_attempts": 0,
        "mutations": 0,
        "deletion_authorized": False,
        "deployment_authorized": False,
    }


def main() -> int:
    print(json.dumps(report(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
