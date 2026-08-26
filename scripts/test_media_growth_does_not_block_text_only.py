#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_autonomous_loop import build_autonomous_plan

auto = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
media = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))

assert media["production_autopilot_enabled"] is True
assert media["media_schedule_enabled"] is True
assert auto["allow_media_posts"] is False

for account_id in ("night_scout", "liver_manager"):
    plan = build_autonomous_plan(account_id)
    assert plan["safety"]["media_download"] is False
    assert plan["safety"]["video_cut"] is False
    assert plan["safety"]["cloudinary_upload"] is False
    assert "media_posts_not_allowed_initial_scope" not in plan["blocked_reasons"]

print("PASS test_media_growth_does_not_block_text_only.py")
