#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_media_growth_engine import build_media_growth_plan
from media_growth_test_fixtures import fixture_caption_service

video = {
    "source_video_id": "sv_src_lm_yt_user_001_abcdefghijk",
    "source_id": "src_lm_yt_user_001",
    "account_id": "liver_manager",
    "platform": "youtube",
    "source_type": "channel",
    "source_url": "https://youtube.com/channel/UCzFzty7aEd4tw3NqCW6pkLQ",
    "video_id": "abcdefghijk",
    "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
    "original_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
    "title": "real video metadata",
    "duration_seconds": 60,
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "discovery_status": "DISCOVERED",
}
transcript = {
    "transcript_id": f"tr_{video['source_video_id']}",
    "source_video_id": video["source_video_id"],
    "transcription_status": "DONE",
    "transcript_text": "配信で初見が入りやすくなるには、入室時の一言と話題の共有が大事です。",
    "segments_json": '[{"start": 1, "end": 12, "text": "配信で初見が入りやすくなるには入室時の一言が大事です。"}]',
}
plan = build_media_growth_plan(
    "liver_manager",
    apply=True,
    confirm_media_growth=True,
    existing_source_videos=[video],
    existing_transcripts=[transcript],
    caption_service=fixture_caption_service(),
)
checks = [
    ("media growth not blocked", plan["status"] != "BLOCKED"),
    ("source videos preferred", plan["source_videos_source"] == "existing_source_videos"),
    ("clip candidates generated", plan["clip_candidate_count"] > 0),
    ("public text valid", plan["final_public_post_validator"] == "PASS"),
    ("no real download", plan["would_download"] is False),
    ("no real cut", plan["would_cut"] is False),
    ("no real upload", plan["would_upload"] is False),
    ("no real video post", plan["would_post_video"] is False),
    ("schedule aftercare enabled", plan["media_plan"]["schedule_enabled"] is True),
    ("public video auto enabled", plan["media_plan"]["media_public_post_auto_enabled"] is True),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
