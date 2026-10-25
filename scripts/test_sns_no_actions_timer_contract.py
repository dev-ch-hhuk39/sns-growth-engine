#!/usr/bin/env python3
"""Ensure local replacement timers stay scoped, read-only where required."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
OPS=ROOT / "ops/systemd"

class LocalTimerContractTests(unittest.TestCase):
    def test_all_four_local_timer_pairs_present(self):
        for name in ("local-ready-audit", "local-security-health",
                     "local-dependency-audit", "local-chrome-cleanup",
                     "local-missed-slot-audit"):
            with self.subTest(name=name):
                service=(OPS / f"sns-growth-{name}.service").read_text()
                timer=(OPS / f"sns-growth-{name}.timer").read_text()
                self.assertIn("OnCalendar=",timer)
                self.assertIn(f"Unit=sns-growth-{name}.service",timer)
                self.assertIn("Type=oneshot",service)
                self.assertIn("NoNewPrivileges=true",service)
                self.assertIn("ProtectSystem=strict",service)
                self.assertNotIn("gh workflow",service)
                self.assertNotIn("ALLOW_REAL_THREADS_POST=true",service)

    def test_security_ready_and_dependency_are_not_mutating(self):
        for name in ("local-ready-audit","local-security-health","local-dependency-audit","local-missed-slot-audit"):
            s=(OPS / f"sns-growth-{name}.service").read_text()
            self.assertNotIn("ReadWritePaths=",s)
            self.assertNotIn("ExecStartPre=/bin/bash",s)
        ready=(OPS / "sns-growth-local-ready-audit.service").read_text()
        self.assertIn("User=snsrunner",ready)
        self.assertIn("EnvironmentFile=",ready)
        self.assertIn("sns_local_ready_audit.py",ready)
        dep=(OPS / "sns-growth-local-dependency-audit.service").read_text()
        self.assertNotIn("EnvironmentFile=",dep)
        self.assertIn("sns_local_dependency_audit.py",dep)

    def test_cleanup_has_exact_dedicated_write_path(self):
        cleanup=(OPS / "sns-growth-local-chrome-cleanup.service").read_text()
        allow=[r for r in cleanup.splitlines() if r.startswith("ReadWritePaths=")]
        self.assertEqual(len(allow),1)
        self.assertIn("/var/lib/sns-growth-engine/.config/google-chrome/Crash Reports/completed",allow[0])
        self.assertIn("--apply",cleanup)
        self.assertIn("ExecStartPre=",cleanup)
        self.assertIn("User=snsrunner",cleanup)

if __name__=="__main__":
    unittest.main()
