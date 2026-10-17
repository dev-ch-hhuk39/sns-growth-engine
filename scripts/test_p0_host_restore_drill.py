#!/usr/bin/env python3
"""Host wrapper tests. Synthetic SQLite only; never a real VPS or API."""
from __future__ import annotations

import fcntl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from p0_real_delivery_once import initialize_local_db, P0OnceGuard, source_fingerprint
from run_p0_host_restore_drill import CONFIRM, DrillBlocked, host_drill

KEY = "49" * 32


class HostRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sns-host-p0-drill-")
        self.addCleanup(self.temp.cleanup)
        parent = Path(self.temp.name)
        self.runtime = parent / ".buffered-runtime"
        self.shared = self.runtime / "shared"
        self.shared.mkdir(parents=True, mode=0o700)
        self.shared.chmod(0o700)
        self.private = self.shared / "p0_once_private"
        self.private.mkdir(mode=0o700)
        self.private.chmod(0o700)
        self.db = self.private / "once.sqlite3"
        initialize_local_db(str(self.db), explicit_operator_init=True, allow_test_path=True)
        self.envfile = self.shared / "runtime.env"
        self.write_env()
        self.lock = parent / "deployment.lock"
        self.lock.touch()
        self.lock.chmod(0o600)

    def write_env(self, content=None):
        if content is None:
            content = (
                "BUFFERED_POSTING_ENABLED=false\n"
                "SNS_P0_ONCE_GATE_ENABLED=false\n"
                f"SNS_P0_ONCE_DB_PATH={self.db}\n"
                f"SNS_P0_ONCE_HMAC_KEY_HEX={KEY}\n"
            )
        self.envfile.write_text(content)
        self.envfile.chmod(0o600)

    def execute_drill(self, confirmation=CONFIRM):
        return host_drill(
            self.runtime, self.lock,
            confirmation=confirmation, allow_test_path=True,
        )

    def test_empty_private_ledger_restores_without_authorization(self):
        report = self.execute_drill()
        self.assertEqual(report["status"], "RESTORE_REHEARSAL_PASS_NO_CUTOVER")
        self.assertTrue(report["posting_still_disabled"])
        self.assertTrue(report["shared_deploy_lock_held_for_drill"])
        self.assertFalse(report["host_runtime_settings_modified"])
        self.assertFalse(report["production_cutover_authorized"])
        self.assertFalse(report["publish_authorized"])

    def test_claim_is_preserved_and_source_unchanged(self):
        source = source_fingerprint(
            account_id="night_scout", queue_id="night_restore_claim_0001",
            text="非公開の合成テスト",
        )
        P0OnceGuard(str(self.db), bytes.fromhex(KEY), allow_test_path=True).claim(
            account_id="night_scout", queue_id="night_restore_claim_0001",
            source_sha256=source,
        )
        original = self.db.read_bytes()
        report = self.execute_drill()
        self.assertEqual(report["verified_claims"], 1)
        self.assertEqual(original, self.db.read_bytes())

    def test_bad_confirmation_or_missing_lock_refused(self):
        with self.assertRaisesRegex(DrillBlocked, "CONFIRMATION_REQUIRED"):
            self.execute_drill("anything")
        self.lock.unlink()
        with self.assertRaisesRegex(DrillBlocked, "DEPLOY_LOCK_UNAVAILABLE"):
            self.execute_drill()

    def test_deploy_lock_contention_refused(self):
        with self.lock.open("r+b") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(DrillBlocked, "DEPLOYMENT_IN_PROGRESS"):
                self.execute_drill()
            fcntl.flock(handle, fcntl.LOCK_UN)

    def test_posting_or_gate_true_blocks_before_ledger_access(self):
        for unsafe in ("BUFFERED_POSTING_ENABLED=true", "SNS_P0_ONCE_GATE_ENABLED=true"):
            with self.subTest(unsafe=unsafe):
                old = self.envfile.read_text()
                self.write_env(old.replace("BUFFERED_POSTING_ENABLED=false", unsafe)
                               if "BUFFERED" in unsafe else old.replace("SNS_P0_ONCE_GATE_ENABLED=false", unsafe))
                with self.assertRaisesRegex(DrillBlocked, "POSTING_MUST_REMAIN_OFF"):
                    self.execute_drill()
                self.write_env()

    def test_malformed_env_and_duplicate_values_refused(self):
        old = self.envfile.read_text()
        for text in (old + "SNS_P0_ONCE_HMAC_KEY_HEX=aaa\n",
                     old + "FOO=$(touch /tmp/unsafe)\n"):
            self.write_env(text)
            with self.assertRaisesRegex(DrillBlocked, "UNVERIFIABLE"):
                self.execute_drill()

    def test_runtime_env_symlink_and_exposed_permissions_refused(self):
        self.envfile.chmod(0o644)
        with self.assertRaisesRegex(DrillBlocked, "UNVERIFIABLE"):
            self.execute_drill()
        self.write_env()
        moved = self.shared / "real.env"
        self.envfile.rename(moved)
        self.envfile.symlink_to(moved)
        with self.assertRaisesRegex(DrillBlocked, "UNVERIFIABLE"):
            self.execute_drill()

    def test_db_path_must_match_owner_private_expected_path(self):
        self.write_env(self.envfile.read_text().replace(str(self.db), "/elsewhere/any.sqlite3"))
        with self.assertRaisesRegex(DrillBlocked, "EXPECTED_LEDGER_MISMATCH"):
            self.execute_drill()

    def test_runtime_modified_during_drill_fails_closed(self):
        with patch("run_p0_host_restore_drill.run_drill") as mocked:
            mocked.return_value = {"status": "RESTORE_REHEARSAL_PASS_NO_CUTOVER"}
            def tamper(*args, **kwargs):
                self.write_env(self.envfile.read_text() + "ALTERNATE_SETTING=value\n")
                return mocked.return_value
            mocked.side_effect = tamper
            with self.assertRaisesRegex(DrillBlocked, "SETTINGS_CHANGED"):
                self.execute_drill()

    def test_wrong_hmac_key_prevents_false_rehearsal(self):
        source = source_fingerprint(
            account_id="night_scout", queue_id="night_claim_for_wrong_key",
            text="合成のみ",
        )
        P0OnceGuard(str(self.db), bytes.fromhex(KEY), allow_test_path=True).claim(
            account_id="night_scout", queue_id="night_claim_for_wrong_key",
            source_sha256=source,
        )
        self.write_env(self.envfile.read_text().replace(KEY, "50" * 32))
        with self.assertRaisesRegex(DrillBlocked, "UNVERIFIABLE"):
            self.execute_drill()

    def test_published_workflow_is_dispatch_only_with_no_secrets(self):
        import yaml
        yml = (Path(__file__).resolve().parents[1]
               / ".github/workflows/p0-private-restore-readonly-drill.yml")
        text = yml.read_text()
        parsed = yaml.safe_load(text)
        self.assertEqual(set(parsed.get("on", parsed.get(True))), {"workflow_dispatch"})
        job = next(iter(parsed["jobs"].values()))
        self.assertIn("main", job["if"])
        self.assertIn("self-hosted", job["runs-on"])
        self.assertNotIn("SNS_P0_ONCE_HMAC_KEY_HEX", text)
        self.assertNotIn("PUBLISH_ENABLED: \"true\"", text)
        self.assertNotIn("--confirm-real-post", text)
        self.assertIn("READONLY_EPHEMERAL_P0_RESTORE", text)


if __name__ == "__main__":
    unittest.main()
