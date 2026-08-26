#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
auto = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
media = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))

assert auto["auto_post_enabled"] is True
assert auto["allow_media_posts"] is False
assert media["video_post_enabled"] is True

for name in ("autonomous-growth-loop-night-scout.yml", "autonomous-growth-loop-liver-manager.yml"):
    workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    assert 'ALLOW_MEDIA_POSTS: "false"' in workflow
    assert 'ALLOW_VIDEO_DOWNLOAD: "false"' in workflow
    assert 'ALLOW_VIDEO_CUT: "false"' in workflow
    assert 'ALLOW_CLOUDINARY_UPLOAD: "false"' in workflow
    assert 'ALLOW_REAL_X_POST: "false"' in workflow

print("PASS test_media_growth_does_not_break_autonomous_text_posting.py")
