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
import resource
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
MAX_PLAINTEXT = 80 * 1024 * 1024
MAX_SQLITE = 64 * 1024 * 1024
MAX_MANIFEST = 16 * 1024
MAX_APPROVAL = 8192


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
    check(0 < len(raw) <= MAX_PLAINTEXT, "SNAPSHOT_SIZE_INVALID")
    try:
        docs: dict[str, bytes] = {}
        total = 0
        # Iterate lazily rather than getmembers(), which may materialize an
        # arbitrarily long, compressible archive header list in memory.
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            for member in archive:
                name = member.name
                check(name not in docs and name in ESSENTIAL | EXTRA
                      and len(docs) < len(ESSENTIAL | EXTRA),
                      "RESTORE_ARCHIVE_MEMBERS_UNSAFE")
                limit = (MAX_SQLITE if name == "once.sqlite3" else
                         MAX_MANIFEST if name == "manifest.json" else
                         256 if name == "signing_key.hex" else MAX_APPROVAL)
                check(member.isfile() and 0 < member.size <= limit
                      and member.mode & 0o077 == 0
                      and name == Path(name).name,
                      "RESTORE_ARCHIVE_STRUCTURE_UNSAFE")
                total += member.size
                check(total <= MAX_PLAINTEXT,
                      "RESTORE_ARCHIVE_EXPANSION_LIMIT")
                file = archive.extractfile(member)
                check(file is not None, "RESTORE_ARCHIVE_EXTRACT_FAILED")
                content = file.read(limit + 1)
                check(len(content) == member.size,
                      "RESTORE_ARCHIVE_CONTENT_SIZE_INVALID")
                docs[name] = content
        names = set(docs)
        check(ESSENTIAL.issubset(names), "RESTORE_ARCHIVE_MEMBERS_UNSAFE")
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
        if args.scratch_parent is not None:
            parent = args.scratch_parent
            check(parent.is_dir() and not parent.is_symlink()
                  and stat.S_IMODE(parent.stat().st_mode) == 0o700
                  and parent.stat().st_uid == os.getuid(),
                  "RESTORE_SCRATCH_PARENT_UNSAFE")
        # Avoid capture_output=True: an attacker-controlled encrypted file may
        # decompress to unlimited stdout. The child is capped by RLIMIT_FSIZE
        # and the 0600 temporary is never promoted or restored to production.
        with tempfile.TemporaryDirectory(
            prefix="sns-p0-age-decrypt-", dir=args.scratch_parent,
        ) as tmp:
            os.chmod(tmp, 0o700)
            plain_path = Path(tmp) / "decrypted-snapshot.tar.gz"
            fd = os.open(plain_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as out:
                result = subprocess.run(
                    [age, "-d", "-i", str(args.identity_file)],
                    input=ciphertext, stdout=out, stderr=subprocess.DEVNULL,
                    timeout=45, check=False,
                    preexec_fn=lambda: resource.setrlimit(
                        resource.RLIMIT_FSIZE, (MAX_PLAINTEXT, MAX_PLAINTEXT)),
                )
            check(result.returncode == 0 and
                  0 < plain_path.stat().st_size <= MAX_PLAINTEXT,
                  "AGE_DECRYPTION_FAILED_OR_OVERSIZE")
            report = verify_plain_snapshot(
                plain_path.read_bytes(), args.expected_release_sha,
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
