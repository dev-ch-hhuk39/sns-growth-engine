#!/usr/bin/env python3
"""Offline atomic Threads token-store regressions (no credentials/network)."""
from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from threads_token_store import TokenStoreError, store_token, token_path


class TokenStoreAtomicTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = self.root / "tokens"
        self.data = {"account_id": "night_scout", "access_token": "fake-test-token",
                     "expires_at": "2026-12-19T00:00:00+09:00"}

    def test_private_atomic_creation_and_account_isolation(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            target = store_token(self.store, "night_scout", self.data)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), self.data)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.store.stat().st_mode), 0o700)
        self.assertEqual(sorted(x.name for x in self.store.iterdir()), ["night_scout.json"])

    def test_replacement_preserves_single_scoped_file_and_mode(self):
        target = store_token(self.store, "night_scout", self.data)
        second = {**self.data, "access_token": "another-fake-token"}
        self.assertEqual(store_token(self.store, "night_scout", second), target)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), second)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(sorted(x.name for x in self.store.iterdir()), ["night_scout.json"])

    def test_replace_failure_preserves_previous_value_and_cleans_temporary(self):
        target = store_token(self.store, "night_scout", self.data)
        with patch("threads_token_store.os.replace", side_effect=OSError("simulated_replace_fail")):
            with self.assertRaises(OSError):
                store_token(self.store, "night_scout", {**self.data, "access_token": "new"})
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), self.data)
        self.assertEqual(sorted(x.name for x in self.store.iterdir()), ["night_scout.json"])

    def test_fsync_failure_before_commit_preserves_previous_value(self):
        target = store_token(self.store, "night_scout", self.data)
        with patch("threads_token_store.os.fsync", side_effect=OSError("simulated_sync_fail")):
            with self.assertRaises(OSError):
                store_token(self.store, "night_scout", {**self.data, "access_token": "new"})
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), self.data)
        self.assertEqual(sorted(x.name for x in self.store.iterdir()), ["night_scout.json"])

    def test_symlink_directory_and_token_are_rejected_without_following(self):
        other = self.root / "other"
        other.mkdir()
        link = self.root / "link"
        link.symlink_to(other, target_is_directory=True)
        with self.assertRaises(TokenStoreError):
            store_token(link, "night_scout", self.data)
        self.assertEqual(list(other.iterdir()), [])
        self.store.mkdir()
        actual = self.root / "other-token"
        actual.write_text("not-to-change", encoding="utf-8")
        (self.store / "night_scout.json").symlink_to(actual)
        with self.assertRaises(TokenStoreError):
            store_token(self.store, "night_scout", self.data)
        self.assertEqual(actual.read_text(encoding="utf-8"), "not-to-change")

    def test_hardlinked_token_is_rejected(self):
        target = store_token(self.store, "night_scout", self.data)
        os.link(target, self.root / "second-hardlink")
        with self.assertRaises(TokenStoreError):
            store_token(self.store, "night_scout", self.data)
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), self.data)

    def test_other_writable_directory_is_rejected(self):
        self.store.mkdir()
        self.store.chmod(0o777)
        with self.assertRaises(TokenStoreError):
            store_token(self.store, "night_scout", self.data)
        self.assertFalse((self.store / "night_scout.json").exists())

    def test_invalid_account_cannot_escape_directory(self):
        for account in ("../../etc", "unknown_account", "", "night_scout/other"):
            with self.subTest(account=account):
                with self.assertRaises(TokenStoreError):
                    token_path(self.store, account)
                with self.assertRaises(TokenStoreError):
                    store_token(self.store, account, {**self.data, "account_id": account})

    def test_mismatched_account_and_blank_token_are_rejected(self):
        with self.assertRaises(TokenStoreError):
            store_token(self.store, "liver_manager", self.data)
        with self.assertRaises(TokenStoreError):
            store_token(self.store, "night_scout", {**self.data, "access_token": " "})
        self.assertFalse(self.store.exists())


if __name__ == "__main__":
    unittest.main()
