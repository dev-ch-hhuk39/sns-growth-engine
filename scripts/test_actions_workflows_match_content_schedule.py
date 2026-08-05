#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
schedule = json.loads((ROOT / "config/content_schedule.json").read_text())["accounts"]
files = {
    "night_scout": {
        "text": ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml",
        "direct_reference_media": ROOT / ".github/workflows/direct-reference-media-night-scout.yml",
        "approved_source_clip": ROOT / ".github/workflows/media-growth-post-night-scout.yml",
    },
    "liver_manager": {
        "text": ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml",
        "direct_reference_media": ROOT / ".github/workflows/direct-reference-media-liver-manager.yml",
        "approved_source_clip": ROOT / ".github/workflows/media-growth-post-liver-manager.yml",
    },
}
for account, slots in schedule.items():
    for slot in slots:
        key = slot["post_type"] if slot["post_type"] in {"direct_reference_media", "approved_source_clip"} else "text"
        text = files[account][key].read_text(encoding="utf-8")
        assert slot["slot_id"] in text
        assert f'cron: "{slot["cron_utc"]}"' in text
print("PASS test_actions_workflows_match_content_schedule.py")
