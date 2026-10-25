#!/usr/bin/env python3
"""Static proof that remote publication-review runner remains bounded and no-post."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVICE = (ROOT / "ops/systemd/sns-growth-local-publication-review.service").read_text()
TIMER = (ROOT / "ops/systemd/sns-growth-local-publication-review.timer").read_text()


class LocalReviewTimerContractTests(unittest.TestCase):
    def test_locks_and_scoped_ownership(self):
        for marker in ("User=snsrunner", "Group=snsrunner", "NoNewPrivileges=true",
                       "ProtectSystem=strict", "PrivateTmp=true", "MemoryMax=350M",
                       "sheets-io.lock", "sns_local_publication_review_job.py"):
            self.assertIn(marker, SERVICE)
        self.assertIn("ReadWritePaths=/opt/github-runners/sns-growth-engine/.buffered-runtime/shared/review-board-state", SERVICE)
        self.assertNotIn("ALLOW_REAL_THREADS_POST=true", SERVICE)
        self.assertNotIn("gh workflow", SERVICE)

    def test_two_hour_timer_and_no_actions(self):
        self.assertIn("OnCalendar=*-*-* 01,03,05,07,09,11,13,15,17,19,21,23:25:00 Asia/Tokyo", TIMER)
        self.assertIn("Unit=sns-growth-local-publication-review.service", TIMER)
        self.assertIn("Persistent=true", TIMER)


if __name__ == "__main__":
    unittest.main()
