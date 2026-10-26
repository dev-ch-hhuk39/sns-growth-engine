#!/usr/bin/env python3
"""Only the known slow offline catalog suite receives extra time, not a skip."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_repository_tests import (  # noqa: E402
    EXTERNAL_ENV_PROBES, OPTIONAL_LOCAL_TOOL_PROBES, SLOW_OFFLINE_TEST_TIMEOUTS,
)


class OfflineBudgetTests(unittest.TestCase):
    def test_only_catalog_gets_bounded_extra_time(self):
        self.assertEqual(
            SLOW_OFFLINE_TEST_TIMEOUTS,
            {"test_offline_original_ready_reserve.py": 300},
        )
        self.assertFalse(set(SLOW_OFFLINE_TEST_TIMEOUTS) & EXTERNAL_ENV_PROBES)
        self.assertFalse(set(SLOW_OFFLINE_TEST_TIMEOUTS) & OPTIONAL_LOCAL_TOOL_PROBES)

    def test_no_real_credentials_or_external_probes(self):
        import run_repository_tests as r
        s = (ROOT / "scripts/run_repository_tests.py").read_text()
        self.assertIn("sanitized_environment()", s)
        self.assertIn("subprocess.run(", s)
        self.assertIn("capture_output=True", s)
        self.assertIn("SLOW_OFFLINE_TEST_TIMEOUTS.get(path.name, 0)", s)
        self.assertFalse(set(r.EXTERNAL_ENV_PROBES) == set())


if __name__ == "__main__":
    unittest.main()
