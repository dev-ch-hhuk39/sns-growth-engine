#!/usr/bin/env python3
"""Offline proof that shared resource checks fail closed and owned stages clean up."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "scripts/check_chadult_vps_deploy_preflight.sh"
INSTALLER = ROOT / "scripts/install_buffered_production_runtime.sh"


class ResourceAndStageGuardTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="sns-guard-test-")
        self.addCleanup(self.work.cleanup)
        self.base = Path(self.work.name)
        self.bin_dir = self.base / "bin"
        self.bin_dir.mkdir()
        self.calls = self.base / "sudo-calls.txt"
        self._executable("sudo", '''#!/bin/sh
printf '%s\\n' "$*" >> "$TEST_SUDO_CALLS"
exit "${TEST_SUDO_EXIT:-0}"
''')
        self.env = dict(os.environ, PATH=f"{self.bin_dir}:{os.environ['PATH']}",
                        TEST_SUDO_CALLS=str(self.calls))

    def _executable(self, name: str, contents: str):
        target = self.bin_dir / name
        target.write_text(contents, encoding="utf-8")
        target.chmod(0o755)

    def _call(self, script: Path, *args: str, **kw):
        env = dict(self.env, **kw)
        return subprocess.run(["bash", str(script), *args], env=env,
                              text=True, capture_output=True, check=False)

    def test_minimum_space_and_exact_administrator_command(self):
        result = self._call(PREFLIGHT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text().strip(),
                         "-n /usr/local/sbin/chadult-vps-resource-check --preflight 8")
        self.calls.unlink()
        result = self._call(PREFLIGHT, "--min-free-gib", "12")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls.read_text().strip(),
                         "-n /usr/local/sbin/chadult-vps-resource-check --preflight 12")

    def test_reject_undersized_and_invalid_policy_before_sudo(self):
        for args in [("--min-free-gib", "7"), ("--min-free-gib", "anything"),
                     ("--min-free-gib", "99999"), ("--unknown", "8")]:
            with self.subTest(args=args):
                self.assertNotEqual(self._call(PREFLIGHT, *args).returncode, 0)
        self.assertFalse(self.calls.exists())

    def test_failed_shared_preflight_is_not_bypassed(self):
        result = self._call(PREFLIGHT, TEST_SUDO_EXIT="2")
        self.assertEqual(result.returncode, 78)
        self.assertIn("[BLOCKED]", result.stderr)
        self.assertNotIn("[OK]", result.stdout)

    def _install_fixture(self):
        release_root = self.base / "production"
        releases = release_root / "releases"
        releases.mkdir(parents=True)
        old_sha = "a" * 40
        new_sha = "b" * 40
        old = releases / old_sha
        old.mkdir()
        (release_root / "current").symlink_to(old)
        source = self.base / "checkout"
        (source / "scripts").mkdir(parents=True)
        (source / "scripts/reconcile_due_production_slots.py").write_text("# test\n")
        (source / "requirements.txt").write_text("\n")
        (source / "requirements-media-runtime.txt").write_text("\n")
        self._executable("rsync", '''#!/bin/sh
while [ "$#" -gt 2 ]; do shift; done
cp -R "$1/." "$2/"
''')
        self._executable("python3", '''#!/bin/sh
if [ "${TEST_VENV_FAIL:-0}" = "1" ]; then exit 23; fi
mkdir -p "$3/bin"
printf '#!/bin/sh\\nexit 0\\n' > "$3/bin/pip"
chmod +x "$3/bin/pip"
cp "$3/bin/pip" "$3/bin/python"
''')
        args = ["--source-root", str(source), "--revision", new_sha, "--apply", "--confirm-install", "--stage-only"]
        return release_root, old, releases / new_sha, args

    def test_denied_preflight_has_no_install_mutation(self):
        release_root, old, target, args = self._install_fixture()
        result = self._call(INSTALLER, *args, BUFFERED_RUNTIME_ROOT=str(release_root), TEST_SUDO_EXIT="1")
        self.assertEqual(result.returncode, 78, result.stderr)
        self.assertEqual((release_root / "current").resolve(), old.resolve())
        self.assertFalse(target.exists())
        self.assertFalse(list((release_root / "releases").glob(".stage-*")))

    def test_venv_failure_removes_only_own_stage_and_preserves_current(self):
        release_root, old, target, args = self._install_fixture()
        result = self._call(INSTALLER, *args, BUFFERED_RUNTIME_ROOT=str(release_root), TEST_VENV_FAIL="1")
        self.assertEqual(result.returncode, 23, result.stderr)
        self.assertEqual((release_root / "current").resolve(), old.resolve())
        self.assertFalse(target.exists())
        self.assertFalse(list((release_root / "releases").glob(".stage-*")))

    def test_success_keeps_existing_rollback_and_no_stage(self):
        release_root, old, target, args = self._install_fixture()
        result = self._call(INSTALLER, *args, BUFFERED_RUNTIME_ROOT=str(release_root))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(old.exists())
        self.assertEqual((release_root / "current").resolve(), old.resolve())
        self.assertTrue((target / ".production-release").is_file())
        self.assertFalse(list((release_root / "releases").glob(".stage-*")))

    def test_legacy_implicit_activate_is_blocked(self):
        release_root, old, target, args = self._install_fixture()
        result = self._call(INSTALLER, *args[:-1], BUFFERED_RUNTIME_ROOT=str(release_root))
        self.assertEqual(result.returncode, 64, result.stderr)
        self.assertEqual((release_root / "current").resolve(), old.resolve())
        self.assertFalse(target.exists())

    def test_deploy_has_preflight_before_secret_write_or_switch(self):
        from yaml import safe_load
        workflow = safe_load((ROOT / ".github/workflows/deploy-buffered-production-runtime.yml").read_text())
        steps = workflow["jobs"]["deploy"]["steps"]
        names = [step.get("name", "") for step in steps]
        self.assertLess(names.index("Fail closed on shared VPS disk and RAM preflight"),
                        names.index("Transactional candidate deploy, health, activation and rollback"))
        self.assertIn("--min-free-gib 8", steps[names.index(
            "Fail closed on shared VPS disk and RAM preflight")]["run"])


if __name__ == "__main__":
    unittest.main()
