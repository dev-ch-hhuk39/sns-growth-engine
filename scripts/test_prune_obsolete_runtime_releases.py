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
from prune_obsolete_runtime_releases import candidate_state, run, _apply_under_shared_lock, assert_not_in_use  # noqa: E402
import shutil

CURRENT = "a" * 40
ROLLBACK = "b" * 40
OLD = "c" * 40
OLDER = "d" * 40
OLDEST = "e" * 40


class PruneReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / ".buffered-runtime"
        releases = self.root / "releases"
        releases.mkdir(parents=True)
        (self.root / "shared" / "locks").mkdir(parents=True)
        now = time.time()
        for sha, days in ((CURRENT, 1), (ROLLBACK, 2), (OLD, 14), (OLDER, 15), (OLDEST, 16)):
            directory = releases / sha
            directory.mkdir()
            (directory / "smoke.txt").write_text("immutable")
            (directory / ".production-release").write_text(sha)
            (directory / ".venv" / "bin").mkdir(parents=True)
            (directory / ".venv" / "bin" / "python").symlink_to(sys.executable)
            os.utime(directory, (now - days * 86400, now - days * 86400))
        (self.root / "current").symlink_to(releases / CURRENT)
        (self.root / "previous").symlink_to(releases / ROLLBACK)

    def test_dry_run_is_read_only_and_keeps_current_and_rollback(self):
        result = run(self.root, CURRENT, [OLDER, OLDEST], confirm=False)
        self.assertEqual(result["mode"], "DRY_RUN")
        self.assertEqual(result["kept_count"], 3)
        self.assertEqual(result["emergency"], OLD)
        self.assertTrue((self.root / "releases" / OLD).is_dir())

    def test_locked_retention_removes_only_requested_stale_releases(self):
        # This helper is called by the shared-lock-protected public runner.
        state = candidate_state(self.root, CURRENT, [OLDER, OLDEST])
        before = shutil.disk_usage("/")
        result = {"mode": "APPLY", **state}
        with patch("prune_obsolete_runtime_releases.assert_not_in_use"):
            result = _apply_under_shared_lock(self.root, CURRENT, [OLDER, OLDEST], state, before, result,
                                              self.root / "shared" / "locks")
        self.assertEqual(set(result["removed_releases"]), {OLDER, OLDEST})
        self.assertFalse((self.root / "releases" / OLDEST).exists())
        self.assertTrue((self.root / "releases" / OLD).exists())
        self.assertTrue((self.root / "releases" / CURRENT).exists())
        self.assertTrue((self.root / "releases" / ROLLBACK).exists())

    def test_confirm_without_shared_deploy_lock_blocks(self):
        with self.assertRaisesRegex(RuntimeError, "shared_deploy_lock_unavailable"):
            run(self.root, CURRENT, [OLDER], confirm=True)
        self.assertTrue((self.root / "releases" / OLD).exists())

    def test_protected_current_or_rollback_blocked(self):
        for sha in (CURRENT, ROLLBACK, OLD):
            with self.assertRaisesRegex(RuntimeError, "protected_release_target"):
                candidate_state(self.root, CURRENT, [sha])

    def test_expected_revision_mismatch_blocks(self):
        with self.assertRaisesRegex(RuntimeError, "unexpected_current_release"):
            candidate_state(self.root, OLDER, [OLDEST])

    def test_recent_release_blocks(self):
        target = self.root / "releases" / OLDER
        now = time.time()
        # Another healthy emergency must remain newer than the target.
        os.utime(self.root / "releases" / OLD, (now - 86400, now - 86400))
        os.utime(target, (now - 4 * 86400, now - 4 * 86400))
        with self.assertRaisesRegex(RuntimeError, "target_release_too_recent"):
            candidate_state(self.root, CURRENT, [OLDER])

    def test_symlink_target_blocks(self):
        target = self.root / "releases" / OLDEST
        shutil.rmtree(target)
        target.symlink_to(self.root / "releases" / CURRENT)
        with self.assertRaisesRegex(RuntimeError, "target_not_regular_directory"):
            candidate_state(self.root, CURRENT, [OLDEST])

    def test_only_current_and_previous_blocks_even_old_target(self):
        shutil.rmtree(self.root / "releases" / OLD)
        shutil.rmtree(self.root / "releases" / OLDER)
        shutil.rmtree(self.root / "releases" / OLDEST)
        with self.assertRaisesRegex(RuntimeError, "not_enough_installed_releases_for_retention"):
            candidate_state(self.root, CURRENT, [OLDEST])

    def test_no_healthy_independent_emergency_fails_closed(self):
        for sha in (OLD, OLDER, OLDEST):
            (self.root / "releases" / sha / ".venv" / "bin" / "python").unlink()
        with self.assertRaisesRegex(RuntimeError, "independent_emergency_release_required"):
            candidate_state(self.root, CURRENT, [OLDEST])

    def test_invalid_sha_blocks(self):
        with self.assertRaisesRegex(RuntimeError, "invalid_target_sha"):
            candidate_state(self.root, CURRENT, ["../outside"])



@unittest.skipUnless(sys.platform == "linux", "requires Linux proc inventory")
class PruneProcessInventoryTests(unittest.TestCase):
    """Disposable fake proc fixtures; no VPS process or release is touched."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sns-prune-process-test-")
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.proc_root = self.base / "proc"
        self.proc = self.proc_root / "987654321"
        self.proc.mkdir(parents=True)
        self.target = self.base / "releases" / ("a" * 40)
        self.target.mkdir(parents=True)
        (self.proc / "cmdline").write_bytes(b"python3\0unrelated.py\0")
        (self.proc / "cwd").symlink_to(self.base / "unrelated")
        (self.proc / "fd").mkdir()

    def inspect(self):
        return assert_not_in_use([self.target], proc_root=self.proc_root)

    def test_unrelated_accessible_process_does_not_block(self):
        self.assertIsNone(self.inspect())

    def test_target_in_process_command_line_blocks(self):
        (self.proc / "cmdline").write_bytes(str(self.target / "run.py").encode() + b"\0")
        with self.assertRaisesRegex(RuntimeError, "target_release_in_use"):
            self.inspect()

    def test_active_file_descriptor_blocks(self):
        (self.proc / "fd" / "3").symlink_to(self.target / "payload.dat")
        with self.assertRaisesRegex(RuntimeError, "target_release_open_fd"):
            self.inspect()

    def test_unreadable_command_line_blocks(self):
        with patch("prune_obsolete_runtime_releases.Path.read_bytes",
                   side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(RuntimeError, "process_cmdline_inventory_unknown"):
                self.inspect()

    def test_unreadable_cwd_blocks(self):
        with patch("prune_obsolete_runtime_releases.os.readlink",
                   side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(RuntimeError, "process_cwd_inventory_unknown"):
                self.inspect()

    def test_unreadable_fd_target_blocks(self):
        (self.proc / "fd" / "3").symlink_to(self.base / "unrelated" / "item")
        original_readlink = os.readlink

        def check_readlink(path):
            if Path(path).name == "3":
                raise PermissionError("denied")
            return original_readlink(path)

        with patch("prune_obsolete_runtime_releases.os.readlink",
                   side_effect=check_readlink):
            with self.assertRaisesRegex(RuntimeError, "process_fd_inventory_unknown"):
                self.inspect()

    def test_missing_live_process_cmdline_blocks(self):
        (self.proc / "cmdline").unlink()
        with self.assertRaisesRegex(RuntimeError, "process_cmdline_inventory_unknown"):
            self.inspect()


if __name__ == "__main__":
    unittest.main()
