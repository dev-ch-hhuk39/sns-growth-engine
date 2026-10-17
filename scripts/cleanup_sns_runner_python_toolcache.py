#!/usr/bin/env python3
"""Bounded recovery of reinstallable Python setup-python toolcache on SNS's dedicated runner.

Never touches production .venv, SQLite, Sheets, SNS, shared tools, Docker,
other applications, or source/media. Every candidate is an exact toolcache
Python version, separately guarded under a deployment lock.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path("/opt/github-runners/sns-growth-engine")
DEPLOY_LOCK = Path("/run/lock/chadult-production-deploy.lock")
VERSION = re.compile(r"3\.(?:11|12|13|14)\.\d+(?:\.\d+)?\Z")
MAX_VERSIONS = 5
MIN_AGE_SECONDS = 30 * 60
# Reinstallable setup-python artifacts only. At least 512 MiB must be
# recoverable to justify a guarded cache eviction; live .venv is never touched.
MIN_RECLAIM_BYTES = 512 * 1024 * 1024


class CacheBlocked(RuntimeError):
    """Stable non-sensitive reason codes only."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise CacheBlocked(reason)


def _ordinary_dir(path: Path) -> None:
    try:
        metadata = path.lstat()
    except OSError:
        raise CacheBlocked("SNS_TOOLCACHE_DIRECTORY_MISSING") from None
    require(stat.S_ISDIR(metadata.st_mode) and not path.is_symlink(),
            "SNS_TOOLCACHE_DIRECTORY_UNSAFE")


def _tree_size(path: Path) -> int:
    result = subprocess.run(
        ["du", "-s", "-B1", "--", str(path)],
        capture_output=True, text=True, timeout=90, check=False,
    )
    require(result.returncode == 0, "SNS_TOOLCACHE_SIZE_UNVERIFIABLE")
    try:
        size = int(result.stdout.split()[0])
    except (IndexError, ValueError):
        raise CacheBlocked("SNS_TOOLCACHE_SIZE_UNVERIFIABLE") from None
    require(0 <= size <= 8 * 1024**3, "SNS_TOOLCACHE_SIZE_OUT_OF_BOUNDS")
    return size


def inspect(root: Path, *, allow_test_root: bool = False, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    if not allow_test_root:
        require(sys.platform == "linux" and root == ROOT,
                "SNS_TOOLCACHE_REQUIRES_DEDICATED_LINUX_RUNNER")
    require(root.name == "sns-growth-engine", "SNS_TOOLCACHE_ROOT_NAME_UNSAFE")
    _ordinary_dir(root)
    work = root / "_work"
    tools = work / "_tool"
    target = tools / "Python"
    for path in (work, tools, target):
        _ordinary_dir(path)
        require(path.resolve(strict=True) == path,
                "SNS_TOOLCACHE_PATH_ALIAS_FORBIDDEN")
    entries = sorted(target.iterdir(), key=lambda p: p.name)
    require(0 < len(entries) <= MAX_VERSIONS, "SNS_TOOLCACHE_VERSION_SCOPE_INVALID")
    candidates = []
    for entry in entries:
        require(bool(VERSION.fullmatch(entry.name)), "SNS_TOOLCACHE_UNKNOWN_VERSION_DIR")
        _ordinary_dir(entry)
        require(entry.resolve(strict=True).parent == target,
                "SNS_TOOLCACHE_TARGET_ESCAPES_ROOT")
        require(now - entry.stat().st_mtime >= MIN_AGE_SECONDS,
                "SNS_TOOLCACHE_VERSION_STILL_FRESH")
        # setup-python toolcache must contain only its arch directory and completion marker.
        contents = list(entry.iterdir())
        require(contents and len(contents) <= 4, "SNS_TOOLCACHE_VERSION_SHAPE_INVALID")
        for child in contents:
            require(child.name in {"x64", "x64.complete", "arm64", "arm64.complete"},
                    "SNS_TOOLCACHE_UNKNOWN_CHILD")
            if child.name.endswith(".complete"):
                require(child.is_file() and not child.is_symlink(),
                        "SNS_TOOLCACHE_COMPLETION_MARKER_UNSAFE")
            else:
                _ordinary_dir(child)
        size = _tree_size(entry)
        candidates.append({"version": entry.name, "bytes": size})
    reclaimed = sum(x["bytes"] for x in candidates)
    require(reclaimed >= MIN_RECLAIM_BYTES, "SNS_TOOLCACHE_NOT_ENOUGH_RECLAIMABLE_BYTES")
    return {
        "status": "PASS", "scope": "dedicated_sns_runner_setup_python_toolcache_only",
        "candidate_versions": candidates, "planned_reclaim_bytes": reclaimed,
        "does_not_touch_live_runtime": True, "requires_download_to_regenerate": True,
    }


def _check_processes(target: Path) -> None:
    require(sys.platform == "linux" and Path("/proc").is_dir(),
            "SNS_TOOLCACHE_PROC_SCAN_UNAVAILABLE")
    for proc in Path("/proc").iterdir():
        if not proc.name.isdecimal() or int(proc.name) == os.getpid():
            continue
        try:
            cmd = (proc / "cmdline").read_bytes()
            cwd = os.readlink(proc / "cwd")
            executable = os.readlink(proc / "exe")
        except (OSError, ValueError):
            # If a process appears/disappears while listing, skip it. Do not
            # follow any arbitrary path from a process in our cleanup.
            continue
        label = os.fsencode(str(target))
        if (label in cmd or any(value == str(target) or value.startswith(str(target) + "/")
                                for value in (cwd, executable))):
            raise CacheBlocked("SNS_TOOLCACHE_STILL_IN_USE")


def recover(root: Path = ROOT, *, confirm: bool = False,
            allow_test_root: bool = False, now: float | None = None) -> dict:
    plan = inspect(root, allow_test_root=allow_test_root, now=now)
    if not confirm:
        return {"mode": "DRY_RUN", "mutations_performed": False, **plan}
    raise CacheBlocked("SNS_TOOLCACHE_APPLY_REQUIRES_LOCKED_MAIN_ENTRYPOINT")


def apply_under_lock(root: Path, *, now: float | None = None) -> dict:
    """Acquired only by main; release untouched if another deploy is active."""
    initial = inspect(root, now=now)
    _check_processes(root / "_work/_tool/Python")
    target = root / "_work/_tool/Python"
    before = shutil.disk_usage("/")
    versions = [entry["version"] for entry in initial["candidate_versions"]]
    removed = []
    for version in versions:
        path = target / version
        _ordinary_dir(path)
        require(path.resolve(strict=True).parent == target,
                "SNS_TOOLCACHE_TARGET_ESCAPES_ROOT")
        require(now is None or now - path.stat().st_mtime >= MIN_AGE_SECONDS,
                "SNS_TOOLCACHE_VERSION_STILL_FRESH")
        _check_processes(target)
        shutil.rmtree(path)
        removed.append(version)
    after = shutil.disk_usage("/")
    return {
        "status": "PASS", "mode": "APPLY",
        "scope": initial["scope"], "removed_versions": removed,
        "recovered_bytes": max(0, after.free - before.free),
        "disk_after_free_bytes": after.free,
        "production_state_modified": False,
        "other_projects_modified": False,
        "sns_posting_enabled": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-cleanup", action="store_true")
    args = parser.parse_args()
    try:
        if not args.confirm_cleanup:
            result = recover()
        else:
            if not DEPLOY_LOCK.is_file() or DEPLOY_LOCK.is_symlink():
                raise CacheBlocked("SNS_TOOLCACHE_DEPLOY_LOCK_UNAVAILABLE")
            with DEPLOY_LOCK.open("rb") as lock:
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise CacheBlocked("SNS_TOOLCACHE_DEPLOY_IN_PROGRESS") from None
                try:
                    result = apply_under_lock(ROOT)
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
    except CacheBlocked as error:
        print(json.dumps({"status": "BLOCKED", "reason": str(error),
                          "mutations_performed": False}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"status": "BLOCKED",
                          "reason": "SNS_TOOLCACHE_UNVERIFIED",
                          "mutations_performed": False}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
