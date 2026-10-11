#!/usr/bin/env python3
"""Bounded SNS-only immutable release retention; no access to other services."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}\Z")
DEFAULT_ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime")
MIN_AGE_SECONDS = 7 * 86400


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise RuntimeError(reason)


def candidate_state(root: Path, expected: str, targets: list[str], *, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    require(bool(SHA.fullmatch(expected)), "invalid_expected_current_sha")
    require(0 < len(targets) <= 2 and len(set(targets)) == len(targets), "target_count_out_of_bounds")
    require(all(SHA.fullmatch(value) for value in targets), "invalid_target_sha")
    require(root.name == ".buffered-runtime" and not root.is_symlink() and root.is_dir(), "invalid_runtime_root")
    releases = root / "releases"
    current = root / "current"
    require(releases.is_dir() and not releases.is_symlink(), "invalid_release_directory")
    require(current.is_symlink(), "current_release_pointer_missing")
    current_path = current.resolve(strict=True)
    require(current_path.parent == releases.resolve(strict=True), "current_release_outside_root")
    require(current_path.name == expected, "unexpected_current_release")
    entries = []
    for entry in releases.iterdir():
        if SHA.fullmatch(entry.name) and entry.is_dir() and not entry.is_symlink():
            entries.append(entry)
    require(any(x.name == expected for x in entries), "current_release_not_installed")
    require(len(entries) >= 3, "not_enough_installed_releases_for_retention")
    ordered = sorted(entries, key=lambda item: item.stat().st_mtime, reverse=True)
    rollback = next((item for item in ordered if item.name != expected), None)
    require(rollback is not None, "rollback_release_missing")
    keep = {expected, rollback.name}
    chosen = []
    for sha in targets:
        path = releases / sha
        require(sha not in keep, "protected_release_target")
        require(path.is_dir() and not path.is_symlink(), "target_not_regular_directory")
        require(path.resolve(strict=True).parent == releases.resolve(strict=True), "target_outside_release_root")
        require(now - path.stat().st_mtime >= MIN_AGE_SECONDS, "target_release_too_recent")
        chosen.append(str(path))
    remaining = {p.name for p in entries} - set(targets)
    require(keep.issubset(remaining) and len(remaining) >= 2, "rollback_retention_violation")
    return {"current": expected, "rollback": rollback.name, "targets": chosen, "kept_count": len(remaining)}


def assert_not_in_use(paths: list[Path]) -> None:
    require(sys.platform == "linux" and Path("/proc").is_dir(), "linux_proc_required")
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal() or int(proc.name) == os.getpid():
            continue
        try:
            args = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
            args = ""
        try:
            cwd = os.readlink(proc / "cwd")
        except (FileNotFoundError, ProcessLookupError, PermissionError, OSError):
            cwd = ""
        for path in paths:
            real = str(path)
            require(real not in args and cwd != real and not cwd.startswith(real + "/"), "target_release_in_use")


def run(root: Path, expected: str, targets: list[str], *, confirm: bool) -> dict:
    state = candidate_state(root, expected, targets)
    before = shutil.disk_usage("/")
    result = {"mode": "APPLY" if confirm else "DRY_RUN", **state,
              "disk_before_used_percent": round(before.used / before.total * 100, 2)}
    if not confirm:
        return result
    lockdir = root / "shared" / "locks"
    require(lockdir.is_dir() and not lockdir.is_symlink(), "runtime_lock_directory_missing")
    with (lockdir / "capacity-recovery.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        candidate_state(root, expected, targets)
        paths = [Path(path) for path in state["targets"]]
        assert_not_in_use(paths)
        removed = []
        for path in paths:
            candidate_state(root, expected, [path.name])
            shutil.rmtree(path)
            removed.append(path.name)
        after = shutil.disk_usage("/")
        result.update(removed_releases=removed,
                      disk_after_used_percent=round(after.used / after.total * 100, 2),
                      media_preparation_disk_gate_met=after.used / after.total * 100 < 80,
                      recovered_bytes=max(0, after.free - before.free))
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runtime-root", type=Path, default=DEFAULT_ROOT)
    p.add_argument("--expected-current", required=True)
    p.add_argument("--target", action="append", required=True)
    p.add_argument("--confirm-cleanup", action="store_true")
    a = p.parse_args()
    try:
        result = run(a.runtime_root, a.expected_current, a.target, confirm=a.confirm_cleanup)
    except (RuntimeError, OSError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps({"status": "PASS", **result}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
