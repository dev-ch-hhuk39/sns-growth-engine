#!/usr/bin/env python3
"""Text slots may recover with text; media slots must never do so."""
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
            assert plan["status"] == "SKIPPED_NO_VALID_MEDIA", plan
            assert plan["would_post"] is False, plan
            assert "media_slot_text_fallback_forbidden" in plan["blocked_reasons"], plan
print("PASS test_content_slot_fallback_contract.py")
