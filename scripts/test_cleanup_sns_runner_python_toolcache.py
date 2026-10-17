#!/usr/bin/env python3
"""Offline safety checks; synthetic file trees only, no host cleanup."""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cleanup_sns_runner_python_toolcache import (
    CacheBlocked, MIN_RECLAIM_BYTES, inspect, recover,
)

NOW = time.time() + 4000.0


class CleanupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="sns-cache-synthetic-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "sns-growth-engine"
        self.target = self.root / "_work/_tool/Python"
        self.version = self.target / "3.11.14"
        (self.version / "x64").mkdir(parents=True)
        (self.version / "x64.complete").write_text("ready")
        self.version.touch()
        # Do not query the real toolcache or calculate real size in tests.
        self.size = patch("cleanup_sns_runner_python_toolcache._tree_size",
                          return_value=MIN_RECLAIM_BYTES + 4096)
        self.size.start()
        self.addCleanup(self.size.stop)

    def plan(self):
        return inspect(self.root, allow_test_root=True, now=NOW)

    def test_exact_synthetic_scope_is_dry_run_only(self):
        self.version.touch()
        result = self.plan()
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["does_not_touch_live_runtime"])
        self.assertEqual(result["candidate_versions"][0]["version"], "3.11.14")
        dry_run = recover(self.root, allow_test_root=True, now=NOW)
        self.assertEqual(dry_run["mode"], "DRY_RUN")
        self.assertFalse(dry_run["mutations_performed"])
        self.assertTrue(self.version.exists())

    def test_mac_or_unapproved_root_cannot_apply(self):
        with self.assertRaises(CacheBlocked):
            recover(self.root, allow_test_root=True, now=NOW, confirm=True)
        self.assertTrue(self.version.exists())

    def test_unknown_sibling_cache_blocks(self):
        (self.target / "not-a-python-tool-version").mkdir()
        with self.assertRaisesRegex(CacheBlocked, "UNKNOWN_VERSION"):
            self.plan()
        self.assertTrue(self.version.exists())

    def test_top_level_symlink_is_never_followed(self):
        other = self.root / "unrelated_python"
        other.mkdir()
        (self.target / "3.11.14" / "x64.complete").unlink()
        (self.target / "3.11.14" / "x64").rmdir()
        (self.target / "3.11.14").rmdir()
        (self.target / "3.11.14").symlink_to(other, target_is_directory=True)
        with self.assertRaises(CacheBlocked):
            self.plan()
        self.assertTrue(other.exists())

    def test_unknown_child_fails(self):
        (self.version / "custom.json").write_text("please preserve")
        with self.assertRaisesRegex(CacheBlocked, "UNKNOWN_CHILD"):
            self.plan()
        self.assertTrue((self.version / "custom.json").exists())

    def test_fresh_version_is_protected(self):
        with self.assertRaisesRegex(CacheBlocked, "STILL_FRESH"):
            inspect(self.root, allow_test_root=True, now=self.version.stat().st_mtime + 30)
        self.assertTrue(self.version.exists())

    def test_insufficient_reclaim_fails_closed(self):
        with patch("cleanup_sns_runner_python_toolcache._tree_size", return_value=4):
            with self.assertRaisesRegex(CacheBlocked, "NOT_ENOUGH_RECLAIM"):
                self.plan()
        self.assertTrue(self.version.exists())

    def test_other_app_root_never_passes(self):
        other = self.root.parent / "liveluencer-tool"
        (other / "_work/_tool/Python/3.11.14/x64").mkdir(parents=True)
        with self.assertRaisesRegex(CacheBlocked, "ROOT_NAME_UNSAFE"):
            inspect(other, allow_test_root=True, now=NOW)

    def test_unsupported_version_fails_closed(self):
        (self.target / "3.9.0").mkdir()
        with self.assertRaisesRegex(CacheBlocked, "UNKNOWN_VERSION"):
            self.plan()

    def test_more_than_five_versions_blocks_mass_cleanup(self):
        for version in ("3.11.11", "3.12.9", "3.13.8", "3.13.7", "3.14.0"):
            (self.target / version).mkdir()
        with self.assertRaisesRegex(CacheBlocked, "SCOPE_INVALID"):
            self.plan()

    def test_workflow_never_calls_a_publisher(self):
        import yaml
        workflow = (Path(__file__).resolve().parents[1] /
                    ".github/workflows/sns-runner-toolcache-recovery.yml")
        source = workflow.read_text()
        parsed = yaml.safe_load(source)
        self.assertEqual(set(parsed.get("on", parsed.get(True))), {"workflow_dispatch"})
        job = next(iter(parsed["jobs"].values()))
        self.assertIn("self-hosted", job["runs-on"])
        self.assertIn("main", job["if"])
        self.assertIn('PUBLISH_ENABLED: "false"', source)
        self.assertIn("cleanup_sns_runner_python_toolcache.py", source)
        self.assertNotIn("ALLOW_REAL_THREADS_POST=true", source)
        self.assertNotIn("post --confirm-real-post", source)


if __name__ == "__main__":
    unittest.main()
