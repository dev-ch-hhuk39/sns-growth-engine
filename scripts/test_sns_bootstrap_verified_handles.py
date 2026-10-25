#!/usr/bin/env python3
"""Handle repair is readback-safe, account scoped and secret free."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sns_bootstrap_verified_handles as script


class VerifiedHandleTests(unittest.TestCase):
    def test_exact_update_only_missing(self):
        raw = ("THREADS_ACCESS_TOKEN_NIGHT_SCOUT=PRIVATE_TOKEN\n"
               "THREADS_HANDLE_NIGHT_SCOUT=\"\"\n"
               "THREADS_HANDLE_LIVER_MANAGER=''\n"
               "THREADS_HANDLE_BEAUTY_ACCOUNT=validbeauty\n"
               "BUFFERED_POSTING_ENABLED=false\n")
        result, changes = script.plan(raw, {
            "night_scout": "new_night", "liver_manager": "new_liver",
            "beauty_account": "validbeauty",
        })
        self.assertEqual(changes, 2)
        self.assertIn("THREADS_HANDLE_NIGHT_SCOUT=new_night\n", result)
        self.assertIn("THREADS_HANDLE_LIVER_MANAGER=new_liver\n", result)
        self.assertIn("THREADS_ACCESS_TOKEN_NIGHT_SCOUT=PRIVATE_TOKEN\n", result)
        self.assertIn("BUFFERED_POSTING_ENABLED=false\n", result)

    def test_duplicate_key_and_mismatch_block(self):
        raw = ("THREADS_HANDLE_NIGHT_SCOUT=wrong\n"
               "THREADS_HANDLE_NIGHT_SCOUT=wrong\n"
               "THREADS_HANDLE_LIVER_MANAGER=\"\"\n"
               "THREADS_HANDLE_BEAUTY_ACCOUNT=beauty\n")
        handles = {"night_scout": "correct", "liver_manager": "lm", "beauty_account": "beauty"}
        with self.assertRaises(script.IdentityBlocked):
            script.plan(raw, handles)
        with self.assertRaises(script.IdentityBlocked):
            script.plan(raw.replace("THREADS_HANDLE_NIGHT_SCOUT=wrong\n", "", 1), handles)

    def test_no_live_network_when_identity_missing(self):
        with self.assertRaises(script.IdentityBlocked), patch(
            "sns_bootstrap_verified_handles.urllib.request.build_opener"
        ) as net:
            script.verify_live("night_scout", {"access_token": "", "user_id": "123"})
        net.assert_not_called()

    def test_arbitrary_file_never_accepted(self):
        with tempfile.TemporaryDirectory() as p:
            with self.assertRaises(script.IdentityBlocked):
                script.bootstrap(Path(p) / "runtime.env", apply=True)


if __name__ == "__main__":
    unittest.main()
