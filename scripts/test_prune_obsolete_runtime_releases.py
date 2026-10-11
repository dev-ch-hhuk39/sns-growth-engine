#!/usr/bin/env python3
"""Offline regression for tightly scoped immutable SNS release cleanup."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prune_obsolete_runtime_releases import candidate_state, run  # noqa: E402

CURRENT = "a" * 40
ROLLBACK = "b" * 40
OLD = "c" * 40
OLDER = "d" * 40


class PruneReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / ".buffered-runtime"
        releases = self.root / "releases"
        releases.mkdir(parents=True)
        (self.root / "shared" / "locks").mkdir(parents=True)
        now = time.time()
        for sha, days in ((CURRENT, 1), (ROLLBACK, 2), (OLD, 14), (OLDER, 15)):
            directory = releases / sha
            directory.mkdir()
            (directory / "smoke.txt").write_text("immutable")
            os.utime(directory, (now - days * 86400, now - days * 86400))
        (self.root / "current").symlink_to(releases / CURRENT)

    def test_dry_run_is_read_only_and_keeps_current_and_rollback(self):
        result = run(self.root, CURRENT, [OLD, OLDER], confirm=False)
        self.assertEqual(result["mode"], "DRY_RUN")
        self.assertEqual(result["kept_count"], 2)
        self.assertTrue((self.root / "releases" / OLD).is_dir())

    def test_confirm_removes_only_requested_stale_releases(self):
        with patch("prune_obsolete_runtime_releases.assert_not_in_use"):
            result = run(self.root, CURRENT, [OLD, OLDER], confirm=True)
        self.assertEqual(set(result["removed_releases"]), {OLD, OLDER})
        self.assertFalse((self.root / "releases" / OLD).exists())
        self.assertTrue((self.root / "releases" / CURRENT).exists())
        self.assertTrue((self.root / "releases" / ROLLBACK).exists())

    def test_protected_current_or_rollback_blocked(self):
        for sha in (CURRENT, ROLLBACK):
            with self.assertRaisesRegex(RuntimeError, "protected_release_target"):
                candidate_state(self.root, CURRENT, [sha])

    def test_expected_revision_mismatch_blocks(self):
        with self.assertRaisesRegex(RuntimeError, "unexpected_current_release"):
            candidate_state(self.root, OLD, [OLDER])

    def test_recent_release_blocks(self):
        target = self.root / "releases" / OLD
        now = time.time()
        os.utime(target, (now - 4 * 86400, now - 4 * 86400))
        with self.assertRaisesRegex(RuntimeError, "target_release_too_recent"):
            candidate_state(self.root, CURRENT, [OLD])

    def test_symlink_target_blocks(self):
        target = self.root / "releases" / OLD
        for file in target.iterdir():
            file.unlink()
        target.rmdir()
        target.symlink_to(self.root / "releases" / CURRENT)
        with self.assertRaisesRegex(RuntimeError, "target_not_regular_directory"):
            candidate_state(self.root, CURRENT, [OLD])

    def test_invalid_sha_blocks(self):
        with self.assertRaisesRegex(RuntimeError, "invalid_target_sha"):
            candidate_state(self.root, CURRENT, ["../outside"])


if __name__ == "__main__":
    unittest.main()
