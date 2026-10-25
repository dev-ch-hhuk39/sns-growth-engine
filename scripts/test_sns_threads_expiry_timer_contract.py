#!/usr/bin/env python3
"""Scheduled expiry watch never refreshes, posts, or changes secrets."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "ops/systemd/sns-growth-local-threads-expiry-watch.service").read_text()
TIMER = (ROOT / "ops/systemd/sns-growth-local-threads-expiry-watch.timer").read_text()
SOURCE = (ROOT / "scripts/sns_local_threads_expiry_watch.py").read_text()


class TimerContract(unittest.TestCase):
    def test_exact_owner_and_read_only(self):
        for k in ("User=snsrunner", "Group=snsrunner", "NoNewPrivileges=true",
                  "ProtectSystem=strict", "PrivateTmp=true",
                  "sns_local_threads_expiry_watch.py"):
            self.assertIn(k, SERVICE)
        self.assertNotIn("ReadWritePaths=", SERVICE)
        self.assertNotIn("scripts/refresh_threads_token.py", SERVICE)
        self.assertNotIn("--apply", SERVICE)

    def test_only_read_api_and_daily_trigger(self):
        self.assertIn("OnCalendar=*-*-* 08:05:00 Asia/Tokyo", TIMER)
        self.assertIn("Persistent=true", TIMER)
        self.assertIn('API_URL = "https://graph.threads.net/debug_token"', SOURCE)
        self.assertNotIn("refresh_access_token", SOURCE)
        self.assertNotIn("requests.post", SOURCE)
        self.assertNotIn("os.replace(", SOURCE)
        self.assertNotIn("store_token(", SOURCE)


if __name__ == "__main__":
    unittest.main()
