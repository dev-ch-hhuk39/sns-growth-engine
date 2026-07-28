#!/usr/bin/env python3
"""Media slots must record an explicit skip instead of publishing text."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_slot_text_fallback import build_plan


for account_id, slot_id in (
    ("night_scout", "ns_1800_direct_media"),
    ("night_scout", "ns_2100_clip_media"),
    ("liver_manager", "lm_1600_direct_media"),
    ("liver_manager", "lm_1800_clip_media"),
):
    plan = build_plan(account_id, slot_id, "asset_unavailable", apply=True)
    assert plan["status"] == "SKIPPED_NO_VALID_MEDIA", plan
    assert plan["would_post"] is False, plan
    assert plan["actual_post_type"] == "", plan

print("PASS test_media_slot_text_fallback_forbidden.py")
