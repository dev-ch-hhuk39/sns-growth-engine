#!/usr/bin/env python3
"""Unit contracts for the strictly scoped SNS Python 3.11 bootstrap.

These tests never read a real SNS runtime, download wheels, or execute an
installation. The actual Linux host smoke is a separate explicit PR job.
"""
from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap_sns_python311 import (  # noqa: E402
    BootstrapBlocked, PATCHELF_FILENAME, PATCHELF_PACKAGE, PATCHELF_SHA256,
    TOOLCACHE_PREFIX, obtain_pinned_patchelf, patch_venv_executables,
)


class SnsPython311BootstrapContracts(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="sns-py311-contract-")
        self.addCleanup(d.cleanup)
        self.root = Path(d.name)

    def test_interpreter_and_patch_tool_versions_are_exact(self):
        self.assertEqual(TOOLCACHE_PREFIX.name, "x64")
        self.assertIn("_work/_tool/Python/3.11.17/", str(TOOLCACHE_PREFIX))
        self.assertEqual(PATCHELF_PACKAGE, "patchelf==0.17.2.4")
        self.assertEqual(len(PATCHELF_SHA256), 64)
        self.assertEqual(PATCHELF_FILENAME.split("-")[1], "0.17.2.4")

    def test_malicious_or_changed_patch_wheel_fails_closed(self):
        (self.root / PATCHELF_FILENAME).write_bytes(b"malicious-content")
        with patch("bootstrap_sns_python311.safe_call"):
            with self.assertRaisesRegex(BootstrapBlocked,
                                        "PATCH_TOOL_HASH_MISMATCH"):
                obtain_pinned_patchelf(self.root, {"PIP_NO_CACHE_DIR": "1"})

    def test_patch_only_three_copied_venv_binaries(self):
        venv = self.root / ".venv"
        (venv / "bin").mkdir(parents=True)
        for name in ("python", "python3", "python3.11"):
            (venv / "bin" / name).write_bytes(b"\x7fELFtestbinary")
        patcher = self.root / "patchelf"
        patcher.write_text("mock")
        with patch("bootstrap_sns_python311.safe_call",
                   return_value=str(TOOLCACHE_PREFIX / "lib") + "\n") as call:
            patch_venv_executables(venv, patcher)
        self.assertEqual(call.call_count, 6)
        for name in ("python", "python3", "python3.11"):
            expected = str(venv / "bin" / name)
            self.assertTrue(any(expected in args[0] for args, _ in
                                call.call_args_list))

    def test_symlink_venv_python_is_never_patched(self):
        venv = self.root / ".venv"
        (venv / "bin").mkdir(parents=True)
        (venv / "bin" / "python").symlink_to(sys.executable)
        with patch("bootstrap_sns_python311.safe_call") as call:
            with self.assertRaisesRegex(BootstrapBlocked,
                                        "VENV_BINARY_UNSAFE"):
                patch_venv_executables(venv, self.root / "patchelf")
            call.assert_not_called()

    def test_release_install_uses_patched_python_and_validates_pillow(self):
        root = Path(__file__).resolve().parents[1]
        install = (root / "scripts/install_buffered_production_runtime.sh").read_text()
        requirements = (root / "requirements.txt").read_text()
        self.assertIn("bootstrap_sns_python311.py", install)
        self.assertNotIn('  python3 -m venv "$stage/.venv"', install)
        self.assertIn("PIP_NO_CACHE_DIR=1", install)
        self.assertIn("SNS_RUNTIME_PYTHON_VERSION_MISMATCH", install)
        self.assertIn("SNS_RUNTIME_PILLOW_VERSION_MISMATCH", install)
        self.assertIn("pillow==13.0.0", requirements)
        self.assertNotIn("pillow==12.3.0", requirements)
        ci = (root / "requirements-ci.txt").read_text()
        self.assertIn("Pillow==13.0.0", ci)
        self.assertNotIn("Pillow==12.3.0", ci)

    def test_no_mutation_of_global_python_or_live_pointers_in_source(self):
        source = (Path(__file__).parent / "bootstrap_sns_python311.py").read_text()
        for forbidden in ("apt-get", "sudo ", "systemctl", "rm -rf",
                          "BUFFERED_POSTING_ENABLED=true", "shutil.rmtree(",
                          "docker prune", "/usr/local/lib/libpython"):
            self.assertNotIn(forbidden, source)
        self.assertIn("temporary", source.lower())
        self.assertIn("PATCHELF_SHA256", source)
        self.assertIn("STAGE.fullmatch", source)


if __name__ == "__main__":
    unittest.main()
