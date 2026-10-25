#!/usr/bin/env python3
"""Static safety regression for the next immutable SNS runtime release."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts/install_buffered_production_runtime.sh").read_text(encoding="utf-8")


class SetuptoolsSecurityPin(unittest.TestCase):
    def test_fixed_setuptools_is_staged_and_verified(self):
        self.assertIn('\"setuptools==84.1.0\"', SOURCE)
        self.assertIn('package_version("setuptools") == "84.1.0"', SOURCE)
        self.assertEqual(SOURCE.count("setuptools==84.1.0"), 1)
        self.assertIn("PIP_NO_CACHE_DIR=1", SOURCE)
        self.assertIn("--only-binary=:all:", SOURCE)
        self.assertIn('\"$stage/.venv/bin/python\" -m pip check', SOURCE)

    def test_no_unsafe_live_venv_update_or_headroom_bypass(self):
        stage = SOURCE.index('if [[ "$STAGE_ONLY" == "true" && ! -d "$target" ]]')
        install = SOURCE.index('"setuptools==84.1.0"')
        publish = SOURCE.index('mv "$stage" "$target"')
        self.assertLess(stage, install)
        self.assertLess(install, publish)
        self.assertIn("--min-free-gib 9", SOURCE)
        self.assertIn("--min-free-gib 8", SOURCE)
        self.assertNotRegex(SOURCE, r"(?m)^\\s*rm -rf .*\\.buffered-runtime/releases")
        self.assertIn('"$stage/.venv/bin/python"', SOURCE)
        self.assertFalse(re.search(r"\$RUNTIME_ROOT/current/\.venv/bin/python.*pip install", SOURCE))


if __name__ == "__main__":
    unittest.main()
