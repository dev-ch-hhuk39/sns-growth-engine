#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sheets_client import TAB_DEFINITIONS

required_queue = {"source_video_id", "clip_candidate_id", "media_url", "media_status", "media_required", "duration_seconds", "aspect_ratio"}
required_posted = {"source_video_id", "clip_candidate_id", "media_asset_id", "media_url", "media_status"}
required_clips = {"source_video_id", "clip_candidate_id", "public_post_text", "public_post_validator_status", "upload_status", "post_status"}
checks = [
    required_queue <= set(TAB_DEFINITIONS["queue"]),
    required_posted <= set(TAB_DEFINITIONS["posted_results"]),
    required_clips <= set(TAB_DEFINITIONS["video_clip_candidates"]),
]
print(f"PASS: {sum(checks)} / FAIL: {len(checks)-sum(checks)}")
raise SystemExit(0 if all(checks) else 1)
