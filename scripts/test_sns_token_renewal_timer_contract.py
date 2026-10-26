#!/usr/bin/env python3
"""Verify token renewal is locally scoped and has no publisher/hosted CI."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
S=(ROOT/"ops/systemd/sns-growth-local-threads-token-renewal.service").read_text()
T=(ROOT/"ops/systemd/sns-growth-local-threads-token-renewal.timer").read_text()

class LocalTokenTimerContracts(unittest.TestCase):
    def test_service_is_guarded(self):
        for word in ("User=snsrunner","Group=snsrunner","NoNewPrivileges=true",
                     "ProtectSystem=strict","ProtectHome=true","UMask=0077",
                     "threads-refresh.lock","sns_local_threads_token_renewal.py",
                     "--confirm-token-renewal"):
            self.assertIn(word,S)
        paths=[x for x in S.splitlines() if x.startswith("ReadWritePaths=")]
        self.assertEqual(len(paths),1)
        self.assertTrue(paths[0].endswith("/shared/threads_tokens"))
        self.assertNotIn("GH_TOKEN",S)
        self.assertNotIn("ALLOW_REAL_THREADS_POST=true",S)

    def test_timeout_covers_all_bounded_accounts_and_lock_wait(self):
        seconds = int(next(line.split("=", 1)[1] for line in S.splitlines() if line.startswith("TimeoutStartSec=")))
        self.assertGreaterEqual(seconds, 120 + 3 * (4 * 20 + 30))
        self.assertLessEqual(seconds, 600)

    def test_weekly_timer_and_no_github(self):
        self.assertIn("OnCalendar=Mon *-*-* 09:40:00 Asia/Tokyo",T)
        self.assertIn("Persistent=true",T)
        self.assertIn("Unit=sns-growth-local-threads-token-renewal.service",T)

if __name__=="__main__":
    unittest.main()
