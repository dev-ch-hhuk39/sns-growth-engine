#!/usr/bin/env python3
"""Focused regression checks for the five-slot fallback contract."""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT / "scripts"))
from content_schedule import load_content_schedule, validate_schedule
from run_slot_text_fallback import build_plan

assert not validate_schedule(), validate_schedule()
schedule = load_content_schedule()["accounts"]
for account, slots in schedule.items():
    assert len(slots) == 5
    for slot in slots:
        if slot["post_type"] in {"direct_reference_media", "generated_clip_media"}:
            plan = build_plan(account, slot["slot_id"], "asset_unavailable", apply=False)
            assert plan["status"] == "PLAN_ONLY" and plan["public_post_preview"]
print("PASS test_content_slot_fallback_contract.py")
