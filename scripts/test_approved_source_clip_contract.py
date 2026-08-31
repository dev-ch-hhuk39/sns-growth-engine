#!/usr/bin/env python3
"""Approved source clips must be real permissioned source-video cuts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

from content_schedule import MEDIA_POST_TYPES, load_content_schedule
from media_post_validator import publisher_media_type

CANONICAL_TYPE = "approved_source_clip"
SAVED_TYPE = "saved_approved_source_clip"

LEGACY_BASE = "generated" + "_clip"
LEGACY_SLOT = LEGACY_BASE + "_media"
LEGACY_SAVED = "saved_" + LEGACY_SLOT
SYNTHETIC_PLATFORM = "system_" + "generated_owned"

assert CANONICAL_TYPE in MEDIA_POST_TYPES
assert LEGACY_SLOT not in MEDIA_POST_TYPES
assert publisher_media_type(CANONICAL_TYPE) == "VIDEO"

schedule = load_content_schedule()

for account_id in ("night_scout", "liver_manager"):
    slots = schedule["accounts"][account_id]

    clip_slots = [
        slot
        for slot in slots
        if slot.get("post_type") == CANONICAL_TYPE
    ]

    assert len(clip_slots) == 1, (
        account_id,
        clip_slots,
    )

    assert clip_slots[0].get("fallback_chain") == [SAVED_TYPE]

capability_path = (
    ROOT / "config/production_capability_matrix.json"
)

capability = json.loads(
    capability_path.read_text(encoding="utf-8")
)

assert CANONICAL_TYPE in capability["capabilities"]
assert LEGACY_BASE not in capability["capabilities"]
assert CANONICAL_TYPE in capability["code_evidence"]

production_paths = (
    ROOT / "scripts/content_schedule.py",
    ROOT / "scripts/backfill_missed_content_slots.py",
    ROOT / "scripts/build_live_canary_inventory.py",
    ROOT / "scripts/final_production_contracts.py",
    ROOT / "scripts/media_post_validator.py",
    ROOT / "scripts/process_threads_queue.py",
    ROOT / "scripts/run_media_production_pipeline.py",
    ROOT / "config/content_schedule.json",
    ROOT / "config/media_growth_engine.json",
    ROOT / "config/production_capability_matrix.json",
)

for path in production_paths:
    text = path.read_text(encoding="utf-8")

    assert LEGACY_BASE not in text, (
        path,
        LEGACY_BASE,
    )
    assert LEGACY_SLOT not in text, (
        path,
        LEGACY_SLOT,
    )
    assert LEGACY_SAVED not in text, (
        path,
        LEGACY_SAVED,
    )
    assert SYNTHETIC_PLATFORM not in text, (
        path,
        SYNTHETIC_PLATFORM,
    )

pipeline = (
    ROOT / "scripts/run_media_production_pipeline.py"
).read_text(encoding="utf-8")

assert "build_cut_plan" in pipeline
assert "execute_cut" in pipeline
assert "download_approved_media" in pipeline
assert "cut_approved_clips" in pipeline

cutter = (
    ROOT / "scripts/cut_approved_clips.py"
).read_text(encoding="utf-8")

assert '"ffmpeg"' in cutter
assert '"-ss"' in cutter
assert '"-t"' in cutter
assert "start_seconds" in cutter
assert "end_seconds" in cutter
assert "build_rights_decision" in cutter

print("PASS test_approved_source_clip_contract.py")
