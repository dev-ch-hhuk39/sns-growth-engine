#!/usr/bin/env python3
"""Prevent static Actions cron/slot mappings from drifting from schedule JSON."""
from __future__ import annotations
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
schedule = json.loads((ROOT / "config/content_schedule.json").read_text())["accounts"]
checks = {
    "night_scout": ("autonomous-growth-loop-night-scout.yml", "direct-reference-media-night-scout.yml", "media-growth-post-night-scout.yml"),
    "liver_manager": ("autonomous-growth-loop-liver-manager.yml", "direct-reference-media-liver-manager.yml", "media-growth-post-liver-manager.yml"),
}
for account, files in checks.items():
    text = "\n".join((ROOT / ".github/workflows" / name).read_text() for name in files)
    for slot in schedule[account]:
        assert f'cron: "{slot["cron_utc"]}"' in text, (account, slot["slot_id"], "cron missing")
        assert slot["slot_id"] in text or slot["post_type"] in {"original_text", "reference_text", "pdca_text"}, (account, slot["slot_id"], "slot mapping missing")
print("PASS test_actions_workflows_match_content_schedule.py")
