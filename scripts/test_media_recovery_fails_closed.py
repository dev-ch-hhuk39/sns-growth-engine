#!/usr/bin/env python3
from pathlib import Path

from backfill_missed_content_slots import TERMINAL

root = Path(__file__).resolve().parents[1]
source = (root / "scripts/backfill_missed_content_slots.py").read_text(encoding="utf-8")
schedule = (root / "config/content_schedule.json").read_text(encoding="utf-8")

assert "SKIPPED_POLICY" in TERMINAL
assert "POLICY_SKIPPED_NO_ELIGIBLE_MEDIA" in source
assert "allow_media_slot_safe_text_fallback=True" not in source
assert '"saved_direct_reference_media", "original_text"' not in schedule
assert '"saved_approved_source_clip", "original_text"' not in schedule
print("PASS test_media_recovery_fails_closed.py")
