#!/usr/bin/env python3
"""Only empirically validated text collection may run automatically."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))
blocked = (
    "production_autopilot_enabled",
    "download_enabled",
    "transcription_enabled",
    "clip_candidate_generation_enabled",
    "cut_enabled",
    "upload_enabled",
    "video_post_enabled",
    "cloudinary_upload_enabled",
    "threads_video_post_enabled",
    "source_video_discovery_apply_enabled",
    "media_schedule_enabled",
    "media_public_post_auto_enabled",
    "auto_approve_clip_candidates",
    "auto_save_discovered_videos",
    "auto_save_clip_candidates",
)
checks = {
    "metadata discovery remains available": config["source_video_discovery_enabled"] is True,
    "clip review is required": config["require_clip_review_before_cut"] is True,
    "unverified media actions are disabled": all(config[key] is False for key in blocked),
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
