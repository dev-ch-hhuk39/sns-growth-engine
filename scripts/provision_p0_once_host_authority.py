#!/usr/bin/env python3
"""One-time, fail-closed P0 SQLite/HMAC bootstrap; NEVER activates posting.

Run only on the authorised VPS under its production deploy lock. The secret
stays in a private 0600 local runtime.env, never in CI variables or logs.
A SQLite backup is verified before publishing config atomically. An interrupted
or partial bootstrap is NOT automatically restarted, erased or repaired.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import secrets
import shlex
import sqlite3
import stat
import sys
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

from p0_real_delivery_once import P0OnceGuard, P0OnceBlocked, initialize_local_db
from validate_p0_once_runtime import inspect

DB_DIR = "p0_once_private"
DB_NAME = "once.sqlite3"
BACKUP_NAME = "initial_backup.sqlite3"
SIGNING_KEYS = (
    "SNS_P0_ONCE_GATE_ENABLED", "SNS_P0_ONCE_DB_PATH",
    "SNS_P0_ONCE_HMAC_KEY_HEX",
)
REQUIRED_CONFIRM = "INITIALIZE_PRIVATE_P0_NO_POST"


class BootstrapBlocked(ValueError):
    pass


def _require_private_regular(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise BootstrapBlocked("P0_BOOTSTRAP_ENV_FILE_INVALID")
    st = path.stat()
    if st.st_uid != os.getuid() or not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o600:
        raise BootstrapBlocked("P0_BOOTSTRAP_ENV_OWNER_OR_MODE_INVALID")


def _parse_env(path: Path) -> list[tuple[str, str]]:
    _require_private_regular(path)
    values: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            items = shlex.split(line)
        except ValueError:
            raise BootstrapBlocked("P0_BOOTSTRAP_ENV_SERIALIZATION_INVALID") from None
        if len(items) != 1 or "=" not in items[0]:
            raise BootstrapBlocked("P0_BOOTSTRAP_ENV_SERIALIZATION_INVALID")
        key, value = items[0].split("=", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) or key in seen:
            raise BootstrapBlocked("P0_BOOTSTRAP_ENV_DUPLICATE_OR_INVALID_KEY")
        seen.add(key)
        values.append((key, value))
    return values


def _validate_root(root: Path) -> tuple[Path, Path]:
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise BootstrapBlocked("P0_BOOTSTRAP_RUNTIME_ROOT_UNSAFE")
    shared = root / "shared"
    if shared.is_symlink() or not shared.is_dir():
        raise BootstrapBlocked("P0_BOOTSTRAP_SHARED_ROOT_UNSAFE")
    st = shared.stat()
    if st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o700:
        raise BootstrapBlocked("P0_BOOTSTRAP_SHARED_ROOT_NOT_PRIVATE")
    live = shared / "runtime.env"
    _require_private_regular(live)
    return shared, live


@contextmanager
def _locked(lock_file: Path):
    if lock_file.is_symlink() or not lock_file.is_file():
        raise BootstrapBlocked("P0_BOOTSTRAP_DEPLOY_LOCK_MISSING")
    with lock_file.open("r+b", buffering=0) as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BootstrapBlocked("P0_BOOTSTRAP_DEPLOY_LOCK_BUSY") from None
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _backup_fresh_ledger(db_path: Path, destination: Path) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(destination, flags, 0o600)
    os.close(fd)
    source = sqlite3.connect("file:" + quote(str(db_path), safe="/") + "?mode=ro", uri=True)
    target = sqlite3.connect(str(destination))
    try:
        source.backup(target)
        if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise BootstrapBlocked("P0_BOOTSTRAP_BACKUP_INTEGRITY_FAILED")
        if target.execute("SELECT COUNT(*) FROM sns_p0_once_heads").fetchone()[0] != 0:
            raise BootstrapBlocked("P0_BOOTSTRAP_BACKUP_NOT_EMPTY")
    finally:
        source.close()
        target.close()
    os.chmod(destination, 0o600)
    _require_private_regular(destination)


def bootstrap(
    runtime_root: Path, *, confirm: str,
    lock_path: Path = Path("/run/lock/chadult-production-deploy.lock"),
    allow_test_path: bool = False,
) -> dict[str, object]:
    if confirm != REQUIRED_CONFIRM:
        raise BootstrapBlocked("P0_BOOTSTRAP_EXPLICIT_NO_POST_CONFIRMATION_REQUIRED")
    shared, live = _validate_root(runtime_root)
    with _locked(lock_path):
        before = live.read_bytes()
        assignments = _parse_env(live)
        env = dict(assignments)
        if env.get("BUFFERED_POSTING_ENABLED", "").lower() != "false":
            raise BootstrapBlocked("P0_BOOTSTRAP_POSTING_NOT_DISABLED")
        if any(key in env for key in SIGNING_KEYS):
            raise BootstrapBlocked("P0_BOOTSTRAP_EXISTING_AUTHORITY_NO_REINIT")
        private_dir = shared / DB_DIR
        if private_dir.exists() or private_dir.is_symlink():
            raise BootstrapBlocked("P0_BOOTSTRAP_PARTIAL_OR_EXISTING_DB_NO_REINIT")
        private_dir.mkdir(mode=0o700)
        _fsync_directory(shared)
        db_path = private_dir / DB_NAME
        backup_path = private_dir / BACKUP_NAME
        key_hex = secrets.token_hex(32)
        try:
            initialize_local_db(
                str(db_path), explicit_operator_init=True,
                allow_test_path=allow_test_path,
            )
            ledger = P0OnceGuard(db_path=str(db_path), secret_key=bytes.fromhex(key_hex),
                                 allow_test_path=allow_test_path)
            for account in ("night_scout", "liver_manager"):
                outcome = inspect(ledger, account_id=account)
                if outcome["verified_claims"] != 0 or outcome["verified_send_attempts"] != 0:
                    raise BootstrapBlocked("P0_BOOTSTRAP_LEDGER_NOT_EMPTY")
            _backup_fresh_ledger(db_path, backup_path)
            _require_private_regular(live)
            if live.read_bytes() != before:
                raise BootstrapBlocked("P0_BOOTSTRAP_RUNTIME_ENV_CHANGED")
            new_values = assignments + [
                ("SNS_P0_ONCE_GATE_ENABLED", "false"),
                ("SNS_P0_ONCE_DB_PATH", str(db_path)),
                ("SNS_P0_ONCE_HMAC_KEY_HEX", key_hex),
            ]
            stage = shared / (".p0-bootstrap-env." + secrets.token_hex(12))
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            fd = os.open(stage, flags, 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as writer:
                    for name, value in new_values:
                        writer.write(name + "=" + shlex.quote(value) + "\n")
                    writer.flush()
                    os.fsync(writer.fileno())
                _require_private_regular(stage)
                if dict(_parse_env(stage)).get("SNS_P0_ONCE_GATE_ENABLED") != "false":
                    raise BootstrapBlocked("P0_BOOTSTRAP_GATE_MUST_REMAIN_OFF")
                os.replace(stage, live)
                _fsync_directory(shared)
            finally:
                if stage.exists():
                    stage.unlink()
            if dict(_parse_env(live)).get("SNS_P0_ONCE_HMAC_KEY_HEX") != key_hex:
                raise BootstrapBlocked("P0_BOOTSTRAP_ENV_READBACK_UNKNOWN")
        except Exception:
            # Do not destroy a partial DB or leak a new key; operator must
            # reconcile any partial state before an intentional new init.
            raise
        return {
            "status": "INITIALIZED_DISABLED",
            "posting_enabled": False, "p0_gate_enabled": False,
            "initial_claims": 0, "verified_private_backup": True,
            "would_publish": False, "would_write_sheets": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    try:
        outcome = bootstrap(args.runtime_root, confirm=args.confirm)
    except (BootstrapBlocked, P0OnceBlocked) as err:
        print(json.dumps({"status": "BLOCKED", "reason": str(err)}, sort_keys=True))
        return 78
    except Exception:
        print(json.dumps({"status": "BLOCKED", "reason": "P0_BOOTSTRAP_UNVERIFIED"}, sort_keys=True))
        return 78
    print(json.dumps(outcome, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
