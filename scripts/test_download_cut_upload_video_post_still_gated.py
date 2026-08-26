#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
auto = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
media = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))

assert auto["allow_video_download"] is False
assert auto["allow_video_cut"] is False
assert auto["allow_cloudinary_upload"] is False
assert auto["allow_media_posts"] is False
assert media["download_enabled"] is True
assert media["cut_enabled"] is True
assert media["upload_enabled"] is True
assert media["video_post_enabled"] is True

for name in (
    "media-growth-production.yml",
    "media-growth-production-night-scout.yml",
    "media-growth-post-liver-manager.yml",
    "media-growth-post-night-scout.yml",
    "direct-media-preparation.yml",
):
    workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    assert 'PUBLISH_ENABLED: "false"' in workflow
    assert 'ALLOW_REAL_THREADS_POST: "false"' in workflow

print("PASS test_download_cut_upload_video_post_still_gated.py")
