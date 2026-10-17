#!/usr/bin/env python3
"""Synthetic-only backup and independently signed ledger restore checks."""
from __future__ import annotations

import io
import json
import os
import tarfile
import tempfile
from pathlib import Path

from export_p0_encrypted_offsite_snapshot import ExportBlocked, make_snapshot
from p0_real_delivery_once import initialize_local_db
from verify_p0_encrypted_offsite_snapshot import (
    RestoreBlocked, verify_plain_snapshot,
)

SHA = "b" * 40
KEY = "c" * 64


def fixture(path: Path) -> tuple[Path, Path]:
    root = path / ".buffered-runtime"
    (root / "releases" / SHA).mkdir(parents=True)
    (root / "current").symlink_to(root / "releases" / SHA)
    private = root / "shared" / "p0_once_private"
    private.mkdir(parents=True, mode=0o700)
    private.chmod(0o700)
    db = private / "once.sqlite3"
    initialize_local_db(str(db), explicit_operator_init=True, allow_test_path=True)
    db.chmod(0o600)
    env_file = root / "shared" / "runtime.env"
    env_file.write_text(
        "BUFFERED_POSTING_ENABLED=false\n"
        "SNS_P0_ONCE_GATE_ENABLED=false\n"
        "SNS_P0_AUTONOMY_MODE=canary\n"
        f"SNS_P0_ONCE_DB_PATH={db}\n"
        f"SNS_P0_ONCE_HMAC_KEY_HEX={KEY}\n",
        encoding="utf-8")
    env_file.chmod(0o600)
    return root, env_file


def refused(function, expected_exception: type[Exception]) -> bool:
    try:
        function()
    except expected_exception:
        return True
    return False


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="sns-p0-backup-fixture-") as temp:
        base = Path(temp)
        root, env_file = fixture(base)
        original_db = (root / "shared" / "p0_once_private" / "once.sqlite3").read_bytes()
        clean = make_snapshot(root, test_mode=True)
        report = verify_plain_snapshot(clean, SHA, scratch_parent=base)
        assert report["status"] == "RESTORED_AND_HMAC_VERIFIED_NO_CUTOVER"
        assert report["verified_claims"] == 0 and report["verified_send_attempts"] == 0
        assert report["posting_enabled"] is False
        assert report["restore_to_live_performed"] is False
        assert (root / "shared" / "p0_once_private" / "once.sqlite3").read_bytes() == original_db
        assert refused(lambda: verify_plain_snapshot(clean, "a" * 40), RestoreBlocked)
        assert refused(lambda: verify_plain_snapshot(b"not-a-bundle", SHA), RestoreBlocked)

        with tarfile.open(fileobj=io.BytesIO(clean), mode="r:gz") as tar:
            files = {m.name: tar.extractfile(m).read() for m in tar.getmembers()}
        files["signing_key.hex"] = b"not-an-authenticated-key"
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode="w:gz") as tar:
            for name, payload in files.items():
                ti = tarfile.TarInfo(name)
                ti.mode = 0o600
                ti.size = len(payload)
                tar.addfile(ti, io.BytesIO(payload))
        assert refused(lambda: verify_plain_snapshot(out.getvalue(), SHA), RestoreBlocked)

        # A gzip-compressible metadata bomb must be rejected before expanding
        # a large member into memory or extracting to any live directory.
        bomb = dict(files)
        bomb["manifest.json"] = b"A" * (16 * 1024 + 1)
        for bad in (
            bomb,
            {**files, "surprise-secret.txt": b"x"},
            {**files, "signing_key.hex": b"c" * 65},
        ):
            tarbuf = io.BytesIO()
            with tarfile.open(fileobj=tarbuf, mode="w:gz") as tar:
                for name, data in bad.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mode = 0o600
                    tar.addfile(info, io.BytesIO(data))
            assert refused(
                lambda value=tarbuf.getvalue(): verify_plain_snapshot(value, SHA),
                RestoreBlocked,
            )
        # A valid SQLite backup must still pass after archive size hardening.
        assert verify_plain_snapshot(clean, SHA)["status"] == (
            "RESTORED_AND_HMAC_VERIFIED_NO_CUTOVER"
        )

        s = env_file.read_text()
        env_file.write_text(s.replace("BUFFERED_POSTING_ENABLED=false",
                                      "BUFFERED_POSTING_ENABLED=true"))
        assert refused(lambda: make_snapshot(root, test_mode=True), ExportBlocked)
        env_file.write_text(s.replace("SNS_P0_ONCE_GATE_ENABLED=false",
                                      "SNS_P0_ONCE_GATE_ENABLED=true"))
        assert refused(lambda: make_snapshot(root, test_mode=True), ExportBlocked)
        env_file.write_text(s)
        os.chmod(env_file, 0o644)
        assert refused(lambda: make_snapshot(root, test_mode=True), ExportBlocked)
        assert not (root / "shared" / "p0_once_private" / "approved_text_canary_night_scout.json").exists()
        print("OFFSITE_P0_SNAPSHOT_TESTS_PASS: 12/12")


if __name__ == "__main__":
    main()
