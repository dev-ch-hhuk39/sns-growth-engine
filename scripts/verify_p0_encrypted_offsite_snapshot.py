#!/usr/bin/env python3
"""Restore an encrypted off-host P0 snapshot to disposable local storage.

Never writes a live runtime, never publishes, never sets provider switches.
Validates whole SQLite + existing authenticated P0 event/send chains.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from p0_real_delivery_once import P0OnceGuard
from validate_p0_once_runtime import inspect

SHA40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
SCHEMA = "sns_p0_offsite_encrypted_snapshot_v1"
EXTRA = {"approved_text_canary_night_scout.json",
         "approved_text_canary_liver_manager.json",
         "approved_text_canary.json"}
ESSENTIAL = {"manifest.json", "once.sqlite3", "signing_key.hex"}


class RestoreBlocked(RuntimeError):
    pass


def check(ok: bool, reason: str) -> None:
    if not ok:
        raise RestoreBlocked(reason)


def read_private(path: Path, cap: int) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        try:
            s = os.fstat(fd)
            check(stat.S_ISREG(s.st_mode) and stat.S_IMODE(s.st_mode) == 0o600
                  and s.st_nlink == 1 and 0 < s.st_size <= cap,
                  "PRIVATE_RESTORE_FILE_UNSAFE")
            data = os.read(fd, cap + 1)
            check(len(data) == s.st_size, "PRIVATE_RESTORE_FILE_CHANGED")
            return data
        finally:
            os.close(fd)
    except OSError:
        raise RestoreBlocked("PRIVATE_RESTORE_FILE_UNAVAILABLE") from None


def verify_plain_snapshot(
    raw: bytes, expected_release_sha: str,
    *, scratch_parent: Path | None = None,
) -> dict[str, object]:
    check(SHA40.fullmatch(expected_release_sha) is not None,
          "RESTORE_EXPECTED_SHA_INVALID")
    check(0 < len(raw) <= 80 * 1024 * 1024, "SNAPSHOT_SIZE_INVALID")
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            members = archive.getmembers()
            names = [m.name for m in members]
            check(len(set(names)) == len(names) and ESSENTIAL.issubset(names)
                  and set(names) <= ESSENTIAL | EXTRA,
                  "RESTORE_ARCHIVE_MEMBERS_UNSAFE")
            check(all(m.isfile() and 0 < m.size <= 64 * 1024 * 1024
                      and m.mode & 0o077 == 0 and m.name == Path(m.name).name
                      for m in members), "RESTORE_ARCHIVE_STRUCTURE_UNSAFE")
            docs = {m.name: archive.extractfile(m).read() for m in members}
        meta = json.loads(docs["manifest.json"].decode("utf-8"))
        check(type(meta) is dict and meta.get("schema") == SCHEMA
              and meta.get("release_sha") == expected_release_sha
              and meta.get("posting_disabled_at_capture") is True
              and meta.get("p0_gate_disabled_at_capture") is True
              and meta.get("canary_mode_at_capture") is True
              and meta.get("auto_restore_authorized") is False
              and meta.get("publish_authorized") is False
              and meta.get("restore_must_reconcile_external_sends") is True,
              "RESTORE_MANIFEST_UNTRUSTED")
        check(sorted(set(names) - ESSENTIAL) ==
              meta.get("signed_manifest_names"),
              "RESTORE_SIGNED_APPROVALS_MISMATCH")
        database = docs["once.sqlite3"]
        check(hashlib.sha256(database).hexdigest() ==
              meta.get("ledger_sha256"), "RESTORE_LEDGER_HASH_INVALID")
        key = docs["signing_key.hex"].decode("ascii")
        check(HEX64.fullmatch(key) is not None, "RESTORE_HMAC_KEY_INVALID")
        if scratch_parent is not None:
            check(scratch_parent.is_dir() and not scratch_parent.is_symlink(),
                  "RESTORE_SCRATCH_PARENT_UNSAFE")
        with tempfile.TemporaryDirectory(
            prefix="sns-p0-offsite-restore-", dir=scratch_parent
        ) as folder:
            os.chmod(folder, 0o700)
            dest = Path(folder) / "once.sqlite3"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            fd = os.open(dest, flags, 0o600)
            with os.fdopen(fd, "wb") as writer:
                writer.write(database)
                writer.flush()
                os.fsync(writer.fileno())
            ledger = P0OnceGuard(
                db_path=str(dest), secret_key=bytes.fromhex(key),
                allow_test_path=True)
            result_night = inspect(ledger, account_id="night_scout")
            result_liver = inspect(ledger, account_id="liver_manager")
            with sqlite3.connect(
                "file:" + str(dest) + "?mode=ro", uri=True,
            ) as conn:
                check(conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok",
                      "RESTORE_SQLITE_INTEGRITY_FAILED")
                head_count = conn.execute(
                    "SELECT COUNT(*) FROM sns_p0_once_heads").fetchone()[0]
            check(meta.get("ledger_rows_observed") == head_count,
                  "RESTORE_OBSERVED_COUNT_MISMATCH")
            check(result_night["verified_claims"] == head_count and
                  result_liver["verified_claims"] == head_count,
                  "RESTORE_HMAC_CHAIN_VALIDATION_INCOMPLETE")
            return {
                "status": "RESTORED_AND_HMAC_VERIFIED_NO_CUTOVER",
                "release_sha": expected_release_sha,
                "verified_claims": head_count,
                "verified_send_attempts": result_night["verified_send_attempts"],
                "restore_to_live_performed": False,
                "posting_enabled": False,
                "no_retry_without_provider_reconciliation": True,
            }
    except RestoreBlocked:
        raise
    except Exception:
        raise RestoreBlocked("RESTORE_SNAPSHOT_UNVERIFIABLE") from None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encrypted-file", type=Path, required=True)
    parser.add_argument("--identity-file", type=Path, required=True)
    parser.add_argument("--expected-release-sha", required=True)
    parser.add_argument("--scratch-parent", type=Path, default=None)
    args = parser.parse_args()
    try:
        ciphertext = read_private(args.encrypted_file, 128 * 1024 * 1024)
        read_private(args.identity_file, 65536)
        age = shutil.which("age")
        check(bool(age), "AGE_DECRYPTOR_UNAVAILABLE")
        result = subprocess.run(
            [age, "-d", "-i", str(args.identity_file)],
            input=ciphertext, capture_output=True, timeout=45, check=False,
        )
        check(result.returncode == 0, "AGE_DECRYPTION_FAILED")
        report = verify_plain_snapshot(
            result.stdout, args.expected_release_sha,
            scratch_parent=args.scratch_parent)
    except Exception:
        print(json.dumps({"status": "BLOCKED",
                          "reason": "P0_OFFSITE_RESTORE_DRILL_FAILED",
                          "posting_enabled": False}, sort_keys=True))
        return 78
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
