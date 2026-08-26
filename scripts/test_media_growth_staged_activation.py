#!/usr/bin/env python3
"""Validate activated V1 media while preserving rights/review boundaries."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / "config/media_growth_engine.json").read_text(encoding="utf-8"))
active = (
    "production_autopilot_enabled",
    "download_enabled",
    "transcription_enabled",
    "clip_candidate_generation_enabled",
    "cut_enabled",
    "upload_enabled",
    "video_post_enabled",
    "cloudinary_upload_enabled",
    "threads_video_post_enabled",
    "media_schedule_enabled",
    "media_public_post_auto_enabled",
    "auto_save_discovered_videos",
    "auto_save_clip_candidates",
)
checks = {
    "metadata discovery remains available": config["source_video_discovery_enabled"] is True,
    "bounded discovery persists inventory": config["source_video_discovery_apply_enabled"] is True,
    "registered-source media actions activated": all(config[key] is True for key in active),
    "permission evidence remains mandatory": config["require_permission_evidence"] is True,
    "media validator remains mandatory": config["require_media_validator_before_post"] is True,
    "clip candidate auto-approval remains off": config["auto_approve_clip_candidates"] is False,
    "unknown/reference-only rights remain blocked": all(
        value in config["blocked_rights_statuses"]
        for value in ("unknown", "reference_only", "third_party_reference_only")
    ),
    "clip preparation no longer requires per-clip pre-cut approval": config["require_clip_review_before_cut"] is False,
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
