#!/usr/bin/env python3
"""Offline process-crash, persistence, identity and per-account renewal coverage."""
from __future__ import annotations

import io
import json
import os
from contextlib import ExitStack, redirect_stdout
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sns_local_threads_token_renewal as app


class Crash(BaseException):
    pass


class CrashSafeRenewalTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(app, "STORE", self.root))
        self.creds = {a: {"access_token": "SYNTHETIC_OLD_" + a, "user_id": str(i+1), "app_id": "app1"}
                      for i, a in enumerate(app.ACCOUNTS)}
        env = {"BUFFERED_POSTING_ENABLED": "false", **{
            app.credential_env_names(a)["handle"]: "test_" + a for a in app.ACCOUNTS}}
        self.stack.enter_context(patch.dict(os.environ, env, clear=True))
        self.identity = self.stack.enter_context(patch.object(app, "_verify_live_identity", return_value={"status": "PASS"}))
        self.stack.enter_context(patch.object(app, "resolve_credentials", side_effect=self.resolve))
        self.inspect = self.stack.enter_context(patch.object(app, "check_one", side_effect=self.metadata))
        self.api = self.stack.enter_context(patch.object(app, "refresh_api", side_effect=self.dispatch))

    def resolve(self, account):
        path = self.root / (account + ".json")
        return json.loads(path.read_text()) if path.exists() else dict(self.creds[account])

    def metadata(self, account, credentials, **kwargs):
        now = int(datetime.now(app.JST).timestamp())
        refreshed = "SYNTHETIC_NEW" in credentials["access_token"]
        return {"issued_at": now - (60 if refreshed else 40*86400),
                "expires_at": now + (60 if refreshed else 10)*86400,
                "scopes": ["threads_basic", "threads_content_publish"]}

    def dispatch(self, current):
        account = next(a for a in app.ACCOUNTS if current == self.creds[a]["access_token"])
        marker = self.root / (".refresh-unknown-" + account)
        payload = json.loads(marker.read_text())
        self.assertEqual(payload["state"], "PREPARED")
        self.assertEqual(payload["account_id"], account)
        self.assertNotIn(current, marker.read_text())
        self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
        return "SYNTHETIC_NEW_" + account, 60*86400

    def test_success_is_verified_and_private_before_own_marker_completion(self):
        report = app.run(apply=True, account_id="liver_manager")
        self.assertEqual(report["accounts"], {"liver_manager": "REFRESHED"})
        self.api.assert_called_once()
        path = self.root / "liver_manager.json"
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(path.read_text())["user_id"], "2")
        self.assertFalse((self.root / ".refresh-unknown-liver_manager").exists())
        self.assertNotIn("SYNTHETIC", json.dumps(report))

    def test_process_crash_after_dispatch_leaves_durable_marker_and_prevents_replay(self):
        def crash(token):
            self.dispatch(token)
            raise Crash()
        self.api.side_effect = crash
        with self.assertRaises(Crash):
            app.run(apply=True, account_id="night_scout")
        with self.assertRaisesRegex(app.TokenBlocked, "MANUAL_RECONCILIATION"):
            app.run(apply=True, account_id="night_scout")
        self.api.assert_called_once()

    def test_legacy_marker_is_preserved_byte_for_byte(self):
        marker = self.root / ".refresh-unknown-night_scout"
        marker.write_text("LEGACY_MANUAL_RECONCILIATION\n")
        before = marker.read_bytes()
        with self.assertRaisesRegex(app.TokenBlocked, "MANUAL_RECONCILIATION"):
            app.run(apply=True, account_id="night_scout")
        self.assertEqual(marker.read_bytes(), before)
        self.api.assert_not_called()
        self.inspect.assert_not_called()

    def test_failed_marker_fsync_never_dispatches(self):
        with patch.object(app, "_sync_directory", side_effect=OSError("private")):
            with self.assertRaisesRegex(app.TokenBlocked, "PERSISTENCE_FAILED"):
                app.run(apply=True, account_id="liver_manager")
        self.api.assert_not_called()
        self.assertTrue((self.root / ".refresh-unknown-liver_manager").exists())

    def test_timeout_does_not_retry_or_overwrite_current_token(self):
        self.api.side_effect = TimeoutError("sensitive response")
        with self.assertRaisesRegex(app.TokenBlocked, "MANUAL_RECONCILIATION"):
            app.run(apply=True, account_id="beauty_account")
        self.api.assert_called_once()
        self.assertFalse((self.root / "beauty_account.json").exists())
        self.assertTrue((self.root / ".refresh-unknown-beauty_account").exists())

    def test_not_due_and_dry_run_do_not_create_marker_or_refresh(self):
        self.assertEqual(app.run(apply=False, account_id="liver_manager")["status"], "DRY_RUN")
        self.api.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])
        self.inspect.side_effect = lambda *a, **k: dict(issued_at=1, expires_at=4100000000, scopes=["threads_basic"])
        self.assertEqual(app.run(apply=True, account_id="liver_manager")["accounts"], {"liver_manager": "CURRENT"})
        self.api.assert_not_called()

    def test_too_young_or_unverified_metadata_never_refreshes(self):
        now = int(datetime.now(app.JST).timestamp())
        self.inspect.side_effect = lambda *a, **k: dict(issued_at=now-300, expires_at=now+600, scopes=["threads_basic"])
        with self.assertRaisesRegex(app.TokenBlocked, "NOT_OLD_ENOUGH"):
            app.run(apply=True, account_id="liver_manager")
        self.api.assert_not_called()
        self.inspect.side_effect = ValueError("secret provider body")
        with self.assertRaisesRegex(app.TokenBlocked, "LIFECYCLE_UNVERIFIED"):
            app.run(apply=True, account_id="liver_manager")
        self.api.assert_not_called()

    def test_scope_loss_or_expiry_mismatch_never_saves_and_keeps_marker(self):
        original = self.metadata
        def metadata(account, credentials, **kwargs):
            r = original(account, credentials, **kwargs)
            if "SYNTHETIC_NEW" in credentials["access_token"]:
                r["scopes"] = ["threads_basic"]
            return r
        self.inspect.side_effect = metadata
        with self.assertRaisesRegex(app.TokenBlocked, "MANUAL_RECONCILIATION"):
            app.run(apply=True, account_id="liver_manager")
        self.assertFalse((self.root / "liver_manager.json").exists())
        self.assertTrue((self.root / ".refresh-unknown-liver_manager").exists())

    def test_failed_persistence_keeps_marker(self):
        with patch.object(app, "store_token", side_effect=OSError("private")):
            with self.assertRaisesRegex(app.TokenBlocked, "MANUAL_RECONCILIATION"):
                app.run(apply=True, account_id="liver_manager")
        self.assertTrue((self.root / ".refresh-unknown-liver_manager").exists())

    def test_completion_never_removes_another_marker_or_symlink(self):
        lease = app.begin_refresh("liver_manager", "synthetic")
        path = self.root / ".refresh-unknown-liver_manager"
        path.write_text('{"state":"PREPARED","account_id":"liver_manager","operation_id":"different"}')
        with self.assertRaises(app.TokenBlocked):
            app.complete_refresh("liver_manager", lease)
        self.assertTrue(path.exists())
        path.unlink()
        target = self.root / "protected"
        target.write_text("do not change")
        path.symlink_to(target)
        with self.assertRaises(app.TokenBlocked):
            app.complete_refresh("liver_manager", lease)
        self.assertEqual(target.read_text(), "do not change")

    def test_unsafe_token_file_blocks_before_credentials_or_network(self):
        path = self.root / "liver_manager.json"
        path.symlink_to(self.root / "missing")
        with patch.object(app, "resolve_credentials") as resolve:
            with self.assertRaisesRegex(app.TokenBlocked, "PRIVATE_REGULAR"):
                app.run(apply=True, account_id="liver_manager")
            resolve.assert_not_called()
        self.api.assert_not_called()

    def test_main_continues_other_accounts_but_reports_failure(self):
        (self.root / ".refresh-unknown-night_scout").write_text("LEGACY")
        out = io.StringIO()
        with patch.object(app.sys, "argv", ["renewal", "--apply", "--confirm-token-renewal"]), redirect_stdout(out):
            code = app.main()
        report = json.loads(out.getvalue().split("=", 1)[1])
        self.assertEqual(code, 1)
        self.assertEqual(report["accounts"]["night_scout"]["status"], "BLOCKED")
        self.assertEqual(report["accounts"]["liver_manager"]["accounts"], {"liver_manager": "REFRESHED"})
        self.assertEqual(report["accounts"]["beauty_account"]["accounts"], {"beauty_account": "REFRESHED"})
        self.assertEqual(self.api.call_count, 2)
        self.assertNotIn("SYNTHETIC", out.getvalue())


if __name__ == "__main__":
    unittest.main()
