#!/usr/bin/env python3
"""No-network/no-Sheets tests for private host bootstrap and no-post guarantee."""
from __future__ import annotations

import fcntl
import os
import sqlite3
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from provision_p0_once_host_authority import (  # noqa: E402
    REQUIRED_CONFIRM, BootstrapBlocked, _parse_env, bootstrap,
)
from p0_real_delivery_once import P0OnceGuard  # noqa: E402
from validate_p0_once_runtime import inspect  # noqa: E402


class PrivateP0Bootstrap(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sns-p0-bootstrap-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / ".buffered-runtime"
        self.shared = self.root / "shared"
        self.shared.mkdir(parents=True, mode=0o700)
        self.shared.chmod(0o700)
        self.envfile = self.shared / "runtime.env"
        self.envfile.write_text(
            "BUFFERED_POSTING_ENABLED=false\n"
            "SPREADSHEET_ID=opaque_reference\n"
        )
        self.envfile.chmod(0o600)
        self.lock = Path(self.temp.name) / "deploy.lock"
        self.lock.write_text("")
        self.lock.chmod(0o600)

    def provision(self, **kwargs):
        return bootstrap(
            self.root, confirm=kwargs.pop("confirm", REQUIRED_CONFIRM),
            lock_path=kwargs.pop("lock_path", self.lock),
            allow_test_path=True,
            **kwargs,
        )

    def test_clean_bootstrap_remains_disabled_and_has_verified_backup(self):
        original = _parse_env(self.envfile)
        result = self.provision()
        self.assertEqual(result["status"], "INITIALIZED_DISABLED")
        self.assertFalse(result["posting_enabled"])
        self.assertFalse(result["p0_gate_enabled"])
        self.assertFalse(result["would_publish"])
        self.assertFalse(result["would_write_sheets"])
        self.assertTrue(result["verified_private_backup"])
        env = dict(_parse_env(self.envfile))
        for key, value in original:
            self.assertEqual(env[key], value)
        self.assertEqual(env["SNS_P0_ONCE_GATE_ENABLED"], "false")
        key = bytes.fromhex(env["SNS_P0_ONCE_HMAC_KEY_HEX"])
        self.assertEqual(len(key), 32)
        db = Path(env["SNS_P0_ONCE_DB_PATH"])
        self.assertTrue(db.is_file())
        backup = db.parent / "initial_backup.sqlite3"
        self.assertTrue(backup.is_file())
        for p in (db, backup, self.envfile):
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(db.parent.stat().st_mode), 0o700)
        with sqlite3.connect(f"file:{backup}?mode=ro", uri=True) as con:
            self.assertEqual(con.execute("PRAGMA quick_check").fetchone()[0], "ok")
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM sns_p0_once_heads").fetchone()[0], 0)
        ledger = P0OnceGuard(str(db), key, allow_test_path=True)
        self.assertEqual(inspect(ledger, account_id="night_scout")["status"], "PASS")
        self.assertEqual(inspect(ledger, account_id="liver_manager")["status"], "PASS")

    def test_existing_authority_is_never_reset(self):
        self.provision()
        initial = self.envfile.read_bytes()
        with self.assertRaisesRegex(BootstrapBlocked, "EXISTING_AUTHORITY_NO_REINIT"):
            self.provision()
        self.assertEqual(self.envfile.read_bytes(), initial)

    def test_partial_existing_db_cannot_be_overwritten(self):
        prior = self.shared / "p0_once_private"
        prior.mkdir(mode=0o700)
        (prior / "once.sqlite3").write_bytes(b"previous")
        with self.assertRaisesRegex(BootstrapBlocked, "PARTIAL_OR_EXISTING"):
            self.provision()
        self.assertEqual((prior / "once.sqlite3").read_bytes(), b"previous")

    def test_explicit_confirmation_required(self):
        with self.assertRaisesRegex(BootstrapBlocked, "CONFIRMATION_REQUIRED"):
            self.provision(confirm="")
        self.assertFalse((self.shared / "p0_once_private").exists())

    def test_posting_enabled_is_not_bootstrappable(self):
        self.envfile.write_text("BUFFERED_POSTING_ENABLED=true\n")
        self.envfile.chmod(0o600)
        with self.assertRaisesRegex(BootstrapBlocked, "POSTING_NOT_DISABLED"):
            self.provision()
        self.assertFalse((self.shared / "p0_once_private").exists())

    def test_private_env_mode_is_required(self):
        self.envfile.chmod(0o644)
        with self.assertRaisesRegex(BootstrapBlocked, "OWNER_OR_MODE_INVALID"):
            self.provision()
        self.assertFalse((self.shared / "p0_once_private").exists())

    def test_symlinked_env_or_shared_is_refused(self):
        original = self.shared / "settings"
        self.envfile.rename(original)
        self.envfile.symlink_to(original)
        with self.assertRaisesRegex(BootstrapBlocked, "ENV_FILE_INVALID"):
            self.provision()
        self.envfile.unlink()
        original.rename(self.envfile)
        self.shared.rename(self.root / "shared_original")
        self.shared.symlink_to(self.root / "shared_original", target_is_directory=True)
        with self.assertRaisesRegex(BootstrapBlocked, "SHARED_ROOT_UNSAFE"):
            self.provision()

    def test_lock_busy_is_fail_closed(self):
        with self.lock.open("r+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(BootstrapBlocked, "DEPLOY_LOCK_BUSY"):
                self.provision()
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        self.assertFalse((self.shared / "p0_once_private").exists())

    def test_duplicate_or_executable_env_is_refused(self):
        for text in (
            "BUFFERED_POSTING_ENABLED=false\nBUFFERED_POSTING_ENABLED=true\n",
            "BUFFERED_POSTING_ENABLED=false; touch /tmp/unsafe\n",
        ):
            self.envfile.write_text(text)
            self.envfile.chmod(0o600)
            with self.assertRaises(BootstrapBlocked):
                self.provision()
            self.assertFalse((self.shared / "p0_once_private").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
