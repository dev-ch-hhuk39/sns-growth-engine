#!/usr/bin/env python3
"""Dry-run + disposable synthetic pending pointer fixture; never touches VPS."""
import tempfile
import unittest
from pathlib import Path

from resolve_abandoned_sns_pending import PendingBlocked, inspect, run

OLD = "a" * 40
PREV = "c" * 40
FAILED = "b" * 40


class PendingGuardTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(prefix="sns-stale-pointer-tests-")
        self.addCleanup(t.cleanup)
        self.root = Path(t.name) / ".buffered-runtime"
        releases = self.root / "releases"
        releases.mkdir(parents=True)
        for sha in (OLD, PREV, FAILED):
            (releases / sha).mkdir()
            (releases / sha / ".production-release").write_text(sha + "\n")
        for label, sha in (("current", OLD), ("previous", PREV), ("pending", FAILED)):
            (self.root / label).symlink_to(releases / sha)
        shared = self.root / "shared"
        shared.mkdir()
        self.env = shared / "runtime.env"
        self.env.write_text(
            "BUFFERED_POSTING_ENABLED=false\n"
            "SNS_P0_ONCE_GATE_ENABLED=false\n"
            "SNS_P0_AUTONOMY_MODE=canary\n")
        self.env.chmod(0o600)
        self.lock = Path(t.name) / "shared-lock"
        self.lock.write_text("")
        self.lock.chmod(0o600)

    def call(self, apply=False):
        return run(OLD, FAILED, apply=apply, root=self.root,
                   lock_path=self.lock, allow_test_root=True)

    def test_exact_dry_run_does_not_modify_anything(self):
        result = self.call()
        self.assertEqual(result["mode"], "DRY_RUN")
        self.assertFalse(result["mutations"])
        self.assertTrue((self.root / "pending").is_symlink())
        self.assertTrue((self.root / "releases" / FAILED).exists())

    def test_apply_unlinks_only_stale_pending_pointer(self):
        result = self.call(apply=True)
        self.assertTrue(result["removed_only_pending_symlink"])
        self.assertFalse((self.root / "pending").exists())
        self.assertTrue((self.root / "current").is_symlink())
        self.assertTrue((self.root / "previous").is_symlink())
        self.assertTrue((self.root / "releases" / FAILED).exists())
        self.assertEqual(self.env.read_text().splitlines()[0],
                         "BUFFERED_POSTING_ENABLED=false")

    def test_wrong_candidate_refuses(self):
        with self.assertRaises(PendingBlocked):
            inspect(self.root, OLD, "d" * 40, allow_test_root=True)
        self.assertTrue((self.root / "pending").exists())

    def test_current_cannot_be_pending(self):
        (self.root / "pending").unlink()
        (self.root / "pending").symlink_to(self.root / "releases" / OLD)
        with self.assertRaises(PendingBlocked):
            self.call(apply=True)

    def test_rollback_release_cannot_be_pending(self):
        (self.root / "pending").unlink()
        (self.root / "pending").symlink_to(self.root / "releases" / PREV)
        with self.assertRaises(PendingBlocked):
            inspect(self.root, OLD, PREV, allow_test_root=True)

    def test_enabled_posting_blocks(self):
        self.env.write_text("BUFFERED_POSTING_ENABLED=true\n"
                            "SNS_P0_ONCE_GATE_ENABLED=false\n")
        with self.assertRaises(PendingBlocked):
            self.call(apply=True)
        self.assertTrue((self.root / "pending").exists())

    def test_symlink_escape_blocks(self):
        outside = self.root.parent / "unrelated-service"
        outside.mkdir()
        (self.root / "pending").unlink()
        (self.root / "pending").symlink_to(outside)
        with self.assertRaises(PendingBlocked):
            self.call(apply=True)
        self.assertTrue(outside.is_dir())

    def test_missing_shared_lock_blocks_apply(self):
        self.lock.unlink()
        with self.assertRaises(PendingBlocked):
            self.call(apply=True)
        self.assertTrue((self.root / "pending").is_symlink())

    def test_no_unscoped_root(self):
        with self.assertRaises(PendingBlocked):
            run(OLD, FAILED, root=self.root, lock_path=self.lock)


if __name__ == "__main__":
    unittest.main()
