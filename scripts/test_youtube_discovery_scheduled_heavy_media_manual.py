#!/usr/bin/env python3
"""Schedules discovery and gated heavy media preparation without publishing."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))

assert config["source_video_discovery_enabled"] is True
assert config["source_video_discovery_apply_enabled"] is True
assert config["download_enabled"] is False
assert config["cut_enabled"] is False
assert config["upload_enabled"] is False
assert config["media_public_post_auto_enabled"] is False

for name in ("media-growth-production.yml", "media-growth-production-night-scout.yml"):
    workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    discovery = workflow.split("- name: Discover approved source videos", 1)[1].split("- name: Transcribe approved source videos", 1)[0]
    heavy = workflow.split("- name: Transcribe approved source videos", 1)[1].split("- name: Clean expired transient media", 1)[0]
    assert "github.event_name == 'schedule'" in discovery
    assert "github.event_name == 'schedule'" in heavy
    assert "github.event.inputs.confirm_production_media == 'true'" in heavy
    assert 'ALLOW_REAL_THREADS_POST: "false"' in workflow
    assert 'PUBLISH_ENABLED: "false"' in workflow

print("PASS test_youtube_discovery_scheduled_heavy_media_manual.py")
