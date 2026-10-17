#!/usr/bin/env python3
"""Encrypt a stopped P0 host ledger snapshot to an operator-owned age recipient.

The ONLY output on stdout is age ciphertext. This does not publish, activate,
alter the source ledger or enable restoration. All raw secret material stays
inside a temporary protected SQLite snapshot and in-memory age input.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import io
import json
import os
import re
import shlex
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime")
LOCK = Path("/run/lock/chadult-production-deploy.lock")
RECIPIENT = re.compile(r"age1[023456789acdefghjklmnpqrstuvwxyz]{35,90}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
KEY = re.compile(r"[0-9a-fA-F]{64}\Z")
MAX_SQLITE_BYTES = 64 * 1024 * 1024
ALLOW_MANIFESTS = ("approved_text_canary_night_scout.json",
                   "approved_text_canary_liver_manager.json",
                   "approved_text_canary.json")


class ExportBlocked(RuntimeError):
    pass


def require(value: bool, reason: str) -> None:
    if not value:
        raise ExportBlocked(reason)


def read_owner_file(path: Path, *, max_size: int, owner_uid: int | None = None) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        try:
            s = os.fstat(fd)
            require(stat.S_ISREG(s.st_mode) and stat.S_IMODE(s.st_mode) == 0o600
                    and s.st_nlink == 1 and 0 < s.st_size <= max_size,
                    "PRIVATE_FILE_MODE_OR_SIZE_UNSAFE")
            if owner_uid is not None:
                require(s.st_uid == owner_uid, "PRIVATE_FILE_OWNER_MISMATCH")
            raw = os.read(fd, max_size + 1)
            require(len(raw) == s.st_size, "PRIVATE_FILE_SIZE_CHANGED")
            return raw
        finally:
            os.close(fd)
    except OSError:
        raise ExportBlocked("PRIVATE_FILE_INACCESSIBLE") from None


def parse_env(raw: bytes) -> dict[str, str]:
    try:
        lines = raw.decode("utf-8").splitlines()
        values = {}
        for line in lines:
            if not line.strip():
                continue
            items = shlex.split(line)
            require(len(items) == 1 and "=" in items[0],
                    "RUNTIME_ENV_SERIALIZATION_INVALID")
            k, v = items[0].split("=", 1)
            require(re.fullmatch(r"[A-Z][A-Z0-9_]*", k) is not None
                    and k not in values, "RUNTIME_ENV_KEYS_INVALID")
            values[k] = v
        return values
    except (ValueError, UnicodeDecodeError):
        raise ExportBlocked("RUNTIME_ENV_SERIALIZATION_INVALID") from None


@contextmanager
def host_lock(path: Path):
    require(path.is_file() and not path.is_symlink(),
            "SHARED_DEPLOY_LOCK_NOT_PRESENT")
    with path.open("r+b", buffering=0) as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise ExportBlocked("SHARED_DEPLOY_LOCK_BUSY") from None
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def add_member(tar: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.mode = 0o600
    info.size = len(payload)
    info.mtime = 0
    tar.addfile(info, io.BytesIO(payload))


def source_identity(root: Path) -> str:
    require(root.is_dir() and not root.is_symlink()
            and root.name == ".buffered-runtime", "RUNTIME_ROOT_UNSAFE")
    releases = root / "releases"
    require(releases.is_dir() and not releases.is_symlink(),
            "RUNTIME_RELEASES_UNSAFE")
    current = root / "current"
    require(current.is_symlink(), "CURRENT_RELEASE_LINK_ABSENT")
    path = current.resolve(strict=True)
    require(path.parent == releases.resolve(strict=True)
            and SHA.fullmatch(path.name) is not None,
            "CURRENT_RELEASE_OUTSIDE_SCOPE")
    return path.name


def make_snapshot(root: Path, *, test_mode: bool = False) -> bytes:
    release_sha = source_identity(root)
    shared = root / "shared"
    private = shared / "p0_once_private"
    env_file = shared / "runtime.env"
    db = private / "once.sqlite3"
    require(shared.is_dir() and not shared.is_symlink()
            and private.is_dir() and not private.is_symlink()
            and stat.S_IMODE(private.stat().st_mode) == 0o700,
            "PRIVATE_DIR_INVALID")
    raw_env = read_owner_file(env_file, max_size=256 * 1024)
    v = parse_env(raw_env)
    require(v.get("BUFFERED_POSTING_ENABLED", "").lower() == "false"
            and v.get("SNS_P0_ONCE_GATE_ENABLED", "").lower() == "false",
            "HOST_POSTING_OR_P0_GATE_NOT_DISABLED")
    require(v.get("SNS_P0_AUTONOMY_MODE", "canary") == "canary",
            "HOST_CONTINUOUS_MODE_ACTIVE")
    require(v.get("SNS_P0_ONCE_DB_PATH") == str(db),
            "HOST_LEDGER_PATH_MISMATCH")
    key = v.get("SNS_P0_ONCE_HMAC_KEY_HEX", "")
    require(KEY.fullmatch(key) is not None, "SIGNING_KEY_UNAVAILABLE")
    db_stat = db.stat()
    require(db_stat.st_size <= MAX_SQLITE_BYTES and
            stat.S_IMODE(db_stat.st_mode) == 0o600
            and db_stat.st_nlink == 1 and not db.is_symlink(),
            "LEDGER_FILE_INVALID")
    require(env_file.stat().st_uid == db_stat.st_uid,
            "LEDGER_AND_RUNTIME_OWNER_MISMATCH")
    manifests: dict[str, bytes] = {}
    for name in ALLOW_MANIFESTS:
        p = private / name
        if p.exists() or p.is_symlink():
            manifests[name] = read_owner_file(
                p, max_size=8192, owner_uid=db_stat.st_uid)

    # sqlite3 backup is transactionally consistent; never copy a live WAL file
    # with cp/tar. Temporary plaintext is created 0600 and removed immediately.
    with tempfile.TemporaryDirectory(prefix="sns-p0-snapshot-", dir="/tmp") as tmp:
        os.chmod(tmp, 0o700)
        target_path = Path(tmp) / "snapshot.sqlite3"
        source = sqlite3.connect(
            "file:" + quote(str(db), safe="/") + "?mode=ro", uri=True)
        try:
            target = sqlite3.connect(str(target_path))
            try:
                source.backup(target)
                require(target.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
                        "SQLITE_SNAPSHOT_INTEGRITY_FAILED")
                tables = {r[0] for r in target.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                require("sns_p0_once_heads" in tables,
                        "EXPECTED_LEDGER_TABLE_MISSING")
                heads_count = target.execute(
                    "SELECT COUNT(*) FROM sns_p0_once_heads").fetchone()[0]
            finally:
                target.close()
        finally:
            source.close()
        os.chmod(target_path, 0o600)
        raw_db = target_path.read_bytes()
        require(0 < len(raw_db) <= MAX_SQLITE_BYTES,
                "SQLITE_BACKUP_SIZE_INVALID")
    meta = {
        "schema": "sns_p0_offsite_encrypted_snapshot_v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "release_sha": release_sha,
        "posting_disabled_at_capture": True,
        "p0_gate_disabled_at_capture": True,
        "canary_mode_at_capture": True,
        "ledger_sha256": hashlib.sha256(raw_db).hexdigest(),
        "ledger_rows_observed": heads_count,
        "signed_manifest_names": sorted(manifests),
        "auto_restore_authorized": False,
        "publish_authorized": False,
        "restore_must_reconcile_external_sends": True,
    }
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        add_member(tar, "manifest.json", json.dumps(
            meta, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        add_member(tar, "once.sqlite3", raw_db)
        add_member(tar, "signing_key.hex", key.lower().encode("ascii"))
        for name, body in sorted(manifests.items()):
            add_member(tar, name, body)
    return output.getvalue()


def encrypt(snapshot: bytes, recipient: str) -> bytes:
    require(RECIPIENT.fullmatch(recipient) is not None,
            "RECIPIENT_IDENTITY_INVALID")
    try:
        result = subprocess.run(
            ["/usr/bin/age", "-r", recipient],
            input=snapshot, capture_output=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise ExportBlocked("AGE_ENCRYPTION_UNAVAILABLE") from None
    require(result.returncode == 0 and
            result.stdout.startswith(b"age-encryption.org/v1\n"),
            "AGE_ENCRYPTION_FAILED")
    return result.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipient", required=True)
    args = parser.parse_args()
    try:
        require(os.geteuid() == 0 and sys.platform == "linux",
                "ROOT_LINUX_RUNTIME_REQUIRED")
        with host_lock(LOCK):
            output = encrypt(make_snapshot(ROOT), args.recipient)
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
        return 0
    except Exception:
        # Any exception could embed a secret path or token. Fixed text only.
        print("P0_OFFSITE_ENCRYPTED_SNAPSHOT_BLOCKED", file=sys.stderr)
        return 78


if __name__ == "__main__":
    raise SystemExit(main())
