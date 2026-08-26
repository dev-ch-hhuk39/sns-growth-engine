#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
media = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))
auto = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))

assert media["source_video_discovery_apply_enabled"] is True
assert media["download_enabled"] is True
assert media["cut_enabled"] is True
assert media["upload_enabled"] is True
assert media["video_post_enabled"] is True
assert media["media_schedule_enabled"] is True
assert media["require_permission_evidence"] is True
assert media["auto_approve_clip_candidates"] is False
assert auto["allow_media_posts"] is False
assert auto["allow_video_download"] is False
assert auto["allow_video_cut"] is False
assert auto["allow_cloudinary_upload"] is False
assert "x" in auto["blocked_platforms_for_post"]
print("PASS test_media_growth_roadmap_off_by_default.py")
