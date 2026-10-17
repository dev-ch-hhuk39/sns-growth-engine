#!/usr/bin/env python3
"""Resolve only the SNS-owned pending symlink after a failed no-post deploy.

Never deletes an immutable release, changes current/previous/env/cron, changes
provider or Sheets state, or enables posting. Caller must supply exact SHAs.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
import stat
import sys
from pathlib import Path

ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime")
LOCK = Path("/run/lock/chadult-production-deploy.lock")
SHA = re.compile(r"[0-9a-f]{40}\Z")


class PendingBlocked(RuntimeError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise PendingBlocked(reason)


def _pointer(root: Path, label: str, releases: Path) -> Path:
    pointer = root / label
    require(pointer.is_symlink(), "SNS_POINTER_MISSING_OR_UNSAFE")
    dest = pointer.resolve(strict=True)
    require(dest.parent == releases.resolve(strict=True)
            and dest.is_dir() and not dest.is_symlink()
            and SHA.fullmatch(dest.name) is not None,
            "SNS_POINTER_OUTSIDE_IMMUTABLE_RELEASES")
    return dest


def inspect(root: Path, current_sha: str, pending_sha: str,
            *, allow_test_root: bool = False) -> dict:
    if not allow_test_root:
        require(sys.platform == "linux" and root == ROOT,
                "SNS_ONLY_LINUX_RUNTIME_REQUIRED")
    require(root.name == ".buffered-runtime" and root.is_dir()
            and not root.is_symlink(), "SNS_RUNTIME_ROOT_UNSAFE")
    require(type(current_sha) is str and SHA.fullmatch(current_sha) is not None
            and type(pending_sha) is str and SHA.fullmatch(pending_sha) is not None
            and current_sha != pending_sha, "SNS_RELEASE_IDENTITY_INVALID")
    releases = root / "releases"
    require(releases.is_dir() and not releases.is_symlink(),
            "SNS_RELEASES_DIRECTORY_UNSAFE")
    current = _pointer(root, "current", releases)
    previous = _pointer(root, "previous", releases)
    pending = _pointer(root, "pending", releases)
    require(current.name == current_sha and pending.name == pending_sha
            and pending != previous and pending != current,
            "SNS_PENDING_CURRENT_OR_ROLLBACK_PROTECTED")
    marker = pending / ".production-release"
    require(marker.is_file() and not marker.is_symlink()
            and marker.read_text(encoding="ascii").strip() == pending_sha,
            "SNS_PENDING_RELEASE_MARKER_UNTRUSTED")
    shared = root / "shared"
    require(shared.is_dir() and not shared.is_symlink(),
            "SNS_SHARED_DIRECTORY_UNSAFE")
    env = shared / "runtime.env"
    try:
        meta = env.lstat()
        require(stat.S_ISREG(meta.st_mode) and stat.S_IMODE(meta.st_mode) == 0o600
                and meta.st_nlink == 1, "SNS_RUNTIME_ENV_NOT_OWNER_ONLY")
        config = {}
        for line in env.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            fragments = shlex.split(line)
            require(len(fragments) == 1 and "=" in fragments[0],
                    "SNS_ENV_SERIALIZATION_INVALID")
            key, value = fragments[0].split("=", 1)
            require(key not in config, "SNS_ENV_DUPLICATE_KEYS")
            config[key] = value
        require(config.get("BUFFERED_POSTING_ENABLED") == "false"
                and config.get("SNS_P0_ONCE_GATE_ENABLED") == "false"
                and config.get("SNS_P0_AUTONOMY_MODE", "canary") == "canary",
                "SNS_POSTING_OR_AUTONOMY_ACTIVE")
    except (OSError, ValueError, UnicodeDecodeError):
        raise PendingBlocked("SNS_PRIVATE_ENV_CANNOT_VERIFY") from None
    return {
        "status": "PASS_EXACT_SNS_PENDING_SCOPE",
        "current_sha": current_sha, "pending_sha": pending_sha,
        "protected_rollback_sha": previous.name,
        "release_directory_retained": True,
        "posting_still_disabled": True,
        "other_services_untouched": True,
    }


def run(current_sha: str, pending_sha: str, *, apply: bool = False,
        root: Path = ROOT, lock_path: Path = LOCK,
        allow_test_root: bool = False) -> dict:
    checked = inspect(root, current_sha, pending_sha,
                      allow_test_root=allow_test_root)
    if not apply:
        return {**checked, "mode": "DRY_RUN", "mutations": False}
    require(lock_path.is_file() and not lock_path.is_symlink(),
            "SHARED_DEPLOY_LOCK_UNAVAILABLE")
    try:
        with lock_path.open("rb") as locked:
            try:
                fcntl.flock(locked.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise PendingBlocked("SHARED_DEPLOY_LOCK_BUSY") from None
            try:
                checked = inspect(root, current_sha, pending_sha,
                                  allow_test_root=allow_test_root)
                if not allow_test_root:
                    from prune_obsolete_runtime_releases import assert_not_in_use
                    assert_not_in_use([root / "releases" / pending_sha])
                (root / "pending").unlink()
                return {**checked, "mode": "APPLY",
                        "removed_only_pending_symlink": True,
                        "mutations": True}
            finally:
                fcntl.flock(locked.fileno(), fcntl.LOCK_UN)
    except OSError:
        raise PendingBlocked("PENDING_POINTER_UNLINK_REFUSED") from None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-current", required=True)
    p.add_argument("--expected-pending", required=True)
    p.add_argument("--confirm", default="")
    args = p.parse_args()
    try:
        if args.confirm and args.confirm != "CLEAR_EXACT_PENDING_POINTER_ONLY":
            raise PendingBlocked("SNS_CONFIRMATION_INVALID")
        report = run(args.expected_current, args.expected_pending,
                     apply=bool(args.confirm))
        print(json.dumps(report, sort_keys=True))
        return 0
    except Exception:
        print(json.dumps({"status": "BLOCKED", "mutations": False,
                          "posting_still_disabled": True}, sort_keys=True))
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
