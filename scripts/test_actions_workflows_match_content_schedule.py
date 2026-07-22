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
    texts = {name: (ROOT / ".github/workflows" / name).read_text() for name in files}
    text = "\n".join(texts.values())
    autonomous = texts[files[0]]
    media = "\n".join(texts[name] for name in files[1:])
    for slot in schedule[account]:
        if slot["post_type"] in {"direct_reference_media", "generated_clip_media"}:
            assert slot["slot_id"] in media, (account, slot["slot_id"], "manual media mapping missing")
            assert f'cron: "{slot["cron_utc"]}"' not in media, (account, slot["slot_id"], "media schedule must stay off before canaries")
        else:
            assert f'cron: "{slot["cron_utc"]}"' in autonomous, (account, slot["slot_id"], "text cron missing")
print("PASS test_actions_workflows_match_content_schedule.py")
