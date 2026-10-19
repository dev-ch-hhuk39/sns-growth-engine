#!/usr/bin/env python3
"""Offline regressions for safe SNS VPS privilege and capacity diagnosis."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sns_vps_authority_capability as audit


class SnsVpsAuthorityCapabilityTests(unittest.TestCase):
    def fixture(self, base: Path, now: float) -> Path:
        root = base / ".buffered-runtime"
        releases = root / "releases"
        releases.mkdir(parents=True)
        refs = {
            "current": "a" * 40,
            "previous": "b" * 40,
            "pending": "c" * 40,
            "old": "d" * 40,
            "recent": "e" * 40,
        }
        for name, sha in refs.items():
            folder = releases / sha
            folder.mkdir()
            (folder / ".production-release").write_text(sha, encoding="ascii")
            os.utime(folder, (now - (9 if name == "old" else 1) * 86400,
                              now - (9 if name == "old" else 1) * 86400))
            if name in ("current", "previous", "pending"):
                (root / name).symlink_to(folder, target_is_directory=True)
        return root

    def test_exact_pointer_never_accepts_untrusted_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.fixture(Path(d), 1760000000.0)
            self.assertEqual(audit.exact_pointer(root, "current"), "a" * 40)
            self.assertEqual(audit.exact_pointer(root, "previous"), "b" * 40)
            self.assertEqual(audit.exact_pointer(root, "missing"), "MISSING_OR_UNSAFE")
            (root / "pending").unlink()
            (root / "pending").symlink_to(Path(d), target_is_directory=True)
            self.assertEqual(audit.exact_pointer(root, "pending"), "INVALID")

    def test_age_eligibility_excludes_active_pending_and_recent(self):
        now = 1760000000.0
        with tempfile.TemporaryDirectory() as d:
            root = self.fixture(Path(d), now)
            count, names = audit.age_eligible_candidates(root, now)
            self.assertEqual((count, names), (1, ["d" * 40]))

    def test_marker_or_symlink_candidate_cannot_qualify(self):
        now = 1760000000.0
        with tempfile.TemporaryDirectory() as d:
            root = self.fixture(Path(d), now)
            bad = root / "releases" / ("d" * 40) / ".production-release"
            bad.write_text("not-the-release", encoding="ascii")
            count, names = audit.age_eligible_candidates(root, now)
            self.assertEqual((count, names), (0, []))
            bad.write_text("d" * 40, encoding="ascii")
            symlink = root / "releases" / ("f" * 40)
            symlink.symlink_to(root / "releases" / ("d" * 40))
            count, names = audit.age_eligible_candidates(root, now)
            self.assertEqual((count, names), (1, ["d" * 40]))

    def test_absent_sudo_is_not_permission(self):
        with patch.object(audit.shutil, "which", return_value=None):
            self.assertFalse(audit.sudo_capability("/usr/bin/python3"))
        with patch.object(audit.shutil, "which", return_value="/usr/bin/sudo"), patch.object(
            audit.subprocess, "run", side_effect=OSError("denied")
        ):
            self.assertFalse(audit.sudo_capability("/usr/bin/python3"))

    def test_unknown_proc_visibility_blocks_without_claiming_unused(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.fixture(Path(d), 1760000000.0)
            with patch("prune_obsolete_runtime_releases.assert_not_in_use",
                       side_effect=RuntimeError("process_fd_inventory_unknown")):
                self.assertEqual(audit.process_eligibility(root), "PROCESS_CANNOT_PROVE_UNUSED")
            (root / "pending").unlink()
            self.assertEqual(audit.process_eligibility(root), "NO_VERIFIABLE_PENDING")


if __name__ == "__main__":
    unittest.main()
