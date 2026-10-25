#!/usr/bin/env python3
"""Read-only replacement monitor cannot open the writer's mutation path."""
from __future__ import annotations
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "ops/systemd/sns-growth-local-review-consistency.service").read_text()
TIMER = (ROOT / "ops/systemd/sns-growth-local-review-consistency.timer").read_text()
SCRIPT = (ROOT / "scripts/sns_local_review_consistency_audit.py").read_text()


class ReadonlyTimerContract(unittest.TestCase):
    def test_readonly_service(self):
        for item in (
            "User=snsrunner", "Group=snsrunner", "NoNewPrivileges=true",
            "ProtectSystem=strict", "ProtectHome=true", "Type=oneshot",
            "sheets-io.lock", "sns_local_review_consistency_audit.py",
        ):
            self.assertIn(item, SERVICE)
        self.assertNotIn("ReadWritePaths=", SERVICE)
        self.assertNotIn("allow-real-post", SERVICE)
        self.assertNotIn("ExecStartPre=", SERVICE)

    def test_daily_cadence_and_safe_code(self):
        self.assertIn("OnCalendar=", TIMER)
        self.assertIn("Unit=sns-growth-local-review-consistency.service", TIMER)
        self.assertIn('"sheets_writes": 0', SCRIPT)
        self.assertIn('"social_posts": 0', SCRIPT)
        self.assertNotIn("sheets_write_once", SCRIPT)
        self.assertNotIn(".append_rows(", SCRIPT)
        self.assertNotIn(".batch_update(", SCRIPT)
        self.assertNotIn("update_queue_item(", SCRIPT)


if __name__ == "__main__":
    unittest.main()
