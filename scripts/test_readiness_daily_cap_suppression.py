#!/usr/bin/env python3
"""A full daily cap is an audited safety stop, not an unresolved outage."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from production_inventory import JST  # noqa: E402
from run_production_readiness_acceptance import effective_due_slots  # noqa: E402


now = datetime(2026, 9, 21, 23, 0, tzinfo=JST)
due = [{"account_id": "liver_manager", "slot_id": "lm_2100_pdca"}]
posts = [
    {
        "account_id": "liver_manager",
        "real_post": "true",
        "posted_at": (now - timedelta(hours=index + 1)).isoformat(),
    }
    for index in range(5)
]

effective, suppressed = effective_due_slots("liver_manager", due, posts, now)
assert effective == []
assert suppressed == due

effective, suppressed = effective_due_slots("liver_manager", due, posts[:4], now)
assert effective == due
assert suppressed == []

print("PASS test_readiness_daily_cap_suppression.py")
