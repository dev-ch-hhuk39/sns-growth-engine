#!/usr/bin/env python3
"""Ephemeral, read-only-source restore drill for the P0 one-use Threads ledger.

A successful *temporary* drill is NOT a durable production backup, an operator
attestation, a cutover permit or permission to resend ambiguous attempts.
No Google, Threads or other network calls. Never updates source SQLite.
Only fixed redacted reason codes/counts are printed; source IDs stay private.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sqlite3
import stat
import tempfile
from pathlib import Path
from contextlib import closing
from urllib.parse import quote

from p0_real_delivery_once import (
    ACCOUNTS, P0OnceBlocked, P0OnceGuard, _private_file, _safe_path,
)
from validate_p0_once_runtime import inspect as inspect_p0

TABLES = (
    "sns_p0_once_meta",
    "sns_p0_once_heads",
    "sns_p0_once_events",
    "sns_p0_once_send_attempts",
)
MAX_ROWS_PER_TABLE = 100_000
SOURCE_LIMIT_BYTES = 2 * 1024**3


class DrillBlocked(RuntimeError):
    """Stable safety reason, never raw data or path."""


def _source_path(value: str, *, allow_test_path: bool) -> Path:
    try:
        path = _safe_path(value, allow_test_path=allow_test_path)
        _private_file(path)
        metadata = path.stat()
        if (not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size > SOURCE_LIMIT_BYTES):
            raise DrillBlocked("P0_DRILL_SOURCE_INVALID_OR_OVERSIZED")
        return path
    except P0OnceBlocked:
        raise DrillBlocked("P0_DRILL_SOURCE_UNTRUSTED") from None
    except OSError:
        raise DrillBlocked("P0_DRILL_SOURCE_UNAVAILABLE") from None


def _new_private_file(path: Path) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    os.close(fd)
    _private_file(path)


def _readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect("file:" + quote(str(path), safe="/") + "?mode=ro", uri=True, timeout=5)
    conn.execute("PRAGMA query_only=ON")
    return conn


def _sqlite_backup(source: sqlite3.Connection, output: Path) -> None:
    _new_private_file(output)
    target = sqlite3.connect(str(output), timeout=5)
    try:
        source.backup(target, pages=128, sleep=0.01)
        target.commit()
        if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise DrillBlocked("P0_DRILL_BACKUP_SQLITE_INTEGRITY_FAILED")
    finally:
        target.close()
    _private_file(output)


def _logical_fingerprint(path: Path) -> tuple[tuple[int, ...], bytes]:
    """Digest complete SQLite table contents without exposing IDs or signatures."""
    digest = hashlib.sha256()
    counts: list[int] = []
    connection = _readonly(path)
    try:
        for name in TABLES:  # constant allowlist; no input SQL interpolation
            data = connection.execute(f'SELECT * FROM "{name}"').fetchall()
            if len(data) > MAX_ROWS_PER_TABLE:
                raise DrillBlocked("P0_DRILL_ROW_LIMIT_EXCEEDED")
            counts.append(len(data))
            digest.update(name.encode("ascii"))
            # Stable order independent of row storage/index order after restore.
            for row in sorted(json.dumps(list(row), separators=(",", ":"), ensure_ascii=True)
                              for row in data):
                digest.update(row.encode("ascii"))
                digest.update(b"\x00")
    finally:
        connection.close()
    return tuple(counts), digest.digest()


def run_drill(db_path: str, key: bytes, *, allow_test_path: bool = False) -> dict:
    """Backup an existing ledger to temporary scratch; verify a second restore.

    This does not create/replace operational backups and never writes to the
    input ledger. Scratch files are removed automatically even after failure.
    """
    if not isinstance(key, bytes) or len(key) < 32:
        raise DrillBlocked("P0_DRILL_KEY_INVALID")
    source_path = _source_path(db_path, allow_test_path=allow_test_path)
    before = source_path.stat()
    try:
        with tempfile.TemporaryDirectory(prefix="sns-p0-restore-drill-") as workspace:
            scratch = Path(workspace)
            if stat.S_IMODE(scratch.stat().st_mode) != 0o700:
                raise DrillBlocked("P0_DRILL_SCRATCH_PERMISSIONS_UNSAFE")
            snapshot_path = scratch / "snapshot.sqlite3"
            restored_path = scratch / "restored.sqlite3"
            source = _readonly(source_path)
            try:
                initial_version = source.execute("PRAGMA data_version").fetchone()[0]
                _sqlite_backup(source, snapshot_path)
                end_version = source.execute("PRAGMA data_version").fetchone()[0]
                if initial_version != end_version or source.total_changes:
                    raise DrillBlocked("P0_DRILL_SOURCE_CHANGED_DURING_BACKUP")
            finally:
                source.close()
            first = P0OnceGuard(str(snapshot_path), key, allow_test_path=True)
            accounts_snapshot = [
                inspect_p0(first, account_id=account_id) for account_id in sorted(ACCOUNTS)
            ]
            with closing(_readonly(snapshot_path)) as backup_source:
                _sqlite_backup(backup_source, restored_path)
            restored = P0OnceGuard(str(restored_path), key, allow_test_path=True)
            accounts_restored = [
                inspect_p0(restored, account_id=account_id) for account_id in sorted(ACCOUNTS)
            ]
            if accounts_snapshot != accounts_restored:
                raise DrillBlocked("P0_DRILL_SIGNED_STATE_MISMATCH")
            snap_counts, snap_hash = _logical_fingerprint(snapshot_path)
            restore_counts, restored_hash = _logical_fingerprint(restored_path)
            if snap_counts != restore_counts or not hmac.compare_digest(snap_hash, restored_hash):
                raise DrillBlocked("P0_DRILL_RESTORE_CONTENT_MISMATCH")
            after = source_path.stat()
            if (before.st_ino != after.st_ino or before.st_size != after.st_size
                    or before.st_mtime_ns != after.st_mtime_ns):
                raise DrillBlocked("P0_DRILL_SOURCE_MODIFIED_DURING_RESTORE")
            return {
                "schema": "sns_p0_ephemeral_restore_drill_v1",
                "status": "RESTORE_REHEARSAL_PASS_NO_CUTOVER",
                "source_file_modified_by_drill": False,
                "restored_copy_signature_checked": True,
                "restored_copy_matches_snapshot": True,
                "verified_claims": accounts_restored[0]["verified_claims"],
                "verified_send_attempts": accounts_restored[0]["verified_send_attempts"],
                "durable_backup_retained": False,
                "operator_backup_restore_attested": False,
                "all_external_writers_disabled": False,
                "publish_authorized": False,
                "sheets_write_authorized": False,
                "production_cutover_authorized": False,
            }
    except DrillBlocked:
        raise
    except (P0OnceBlocked, sqlite3.Error, OSError, ValueError, TypeError):
        raise DrillBlocked("P0_DRILL_SOURCE_OR_RESTORED_LEDGER_UNVERIFIABLE") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", help="Existing private ledger path (never created)")
    args = parser.parse_args()
    try:
        key_hex = os.environ.get("SNS_P0_ONCE_HMAC_KEY_HEX", "")
        if (not re.fullmatch(r"[A-Fa-f0-9]{64,}", key_hex)
                or len(key_hex) % 2):
            raise DrillBlocked("P0_DRILL_KEY_NOT_CONFIGURED")
        path = args.db_path or os.environ.get("SNS_P0_ONCE_DB_PATH", "")
        report = run_drill(path, bytes.fromhex(key_hex))
    except DrillBlocked as exc:
        print(json.dumps({
            "schema": "sns_p0_ephemeral_restore_drill_v1", "status": "BLOCKED",
            "reason": str(exc), "publish_authorized": False,
            "production_cutover_authorized": False,
        }, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({
            "schema": "sns_p0_ephemeral_restore_drill_v1", "status": "BLOCKED",
            "reason": "P0_DRILL_UNVERIFIED", "publish_authorized": False,
            "production_cutover_authorized": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
