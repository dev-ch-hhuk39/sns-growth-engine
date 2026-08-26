#!/usr/bin/env python3
"""Scheduled heavy media is active, bounded, and preparation-only."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))

assert config["source_video_discovery_enabled"] is True
assert config["source_video_discovery_apply_enabled"] is True
assert config["download_enabled"] is True
assert config["cut_enabled"] is True
assert config["upload_enabled"] is True
assert config["media_public_post_auto_enabled"] is True
assert config["max_total_new_videos_per_run"] <= 20
assert config["max_failed_retries_per_run"] <= 5

# Legacy per-account preparation workflows may still exist, but preparation
# never publishes. Real posting remains in separately activation-gated workers.
for name in ("media-growth-production.yml", "media-growth-production-night-scout.yml"):
    workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
    assert "github.event_name == 'schedule'" in workflow
    assert 'ALLOW_REAL_THREADS_POST: "false"' in workflow
    assert 'PUBLISH_ENABLED: "false"' in workflow

scheduler = (ROOT / ".github/workflows/media-preparation-scheduler.yml").read_text(encoding="utf-8")
assert "approved-source-clip-preparation.yml/dispatches" in scheduler
assert "direct-media-preparation.yml/dispatches" in scheduler
assert "confirm_preparation" in scheduler
print("PASS test_youtube_discovery_scheduled_heavy_media_manual.py")
