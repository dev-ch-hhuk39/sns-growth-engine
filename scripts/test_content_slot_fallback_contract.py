#!/usr/bin/env python3
"""Text slots may recover with text; media slots must never do so."""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from content_schedule import load_content_schedule, slot_by_id, slots_for_account, validate_schedule  # noqa: E402
from content_slot_runs import build_slot_run  # noqa: E402
from run_slot_text_fallback import build_plan  # noqa: E402

assert not validate_schedule(), validate_schedule()
schedule = load_content_schedule()["accounts"]
for account, slots in schedule.items():
    assert len(slots) == 5
    for slot in slots:
        if slot["post_type"] in {"direct_reference_media", "approved_source_clip"}:
            plan = build_plan(account, slot["slot_id"], "asset_unavailable", apply=False)
            assert plan["status"] == "SKIPPED_NO_VALID_MEDIA", plan
            assert plan["would_post"] is False, plan
            assert "media_slot_text_fallback_forbidden" in plan["blocked_reasons"], plan
beauty_slots = slots_for_account("beauty_account")
assert [slot["slot_id"] for slot in beauty_slots] == ["beauty_1130", "beauty_2030"]
assert slot_by_id("beauty_account", "beauty_2030")["target_jst"] == "20:30"
beauty_direct = slot_by_id("beauty_account", "beauty_direct_media_review")
beauty_clip = slot_by_id("beauty_account", "beauty_clip_review")
assert beauty_direct["post_type"] == "direct_reference_media", beauty_direct
assert beauty_direct["review_only"] is True, beauty_direct
assert beauty_clip["post_type"] == "approved_source_clip", beauty_clip
assert beauty_clip["review_only"] is True, beauty_clip
assert slot_by_id("beauty_account", "unknown_media_slot") is None
assert build_slot_run("beauty_account", "beauty_2030")["slot_id"] == "beauty_2030"
print("PASS test_content_slot_fallback_contract.py")
