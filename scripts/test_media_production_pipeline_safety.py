#!/usr/bin/env python3
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_media_production_pipeline import REQUIRED_ENV, build_plan, select_candidate
from run_media_growth_engine import is_real_discovered_video

for name in REQUIRED_ENV:
    os.environ.pop(name, None)

plan = build_plan(apply=False, confirm=False, client=None)
blocked = build_plan(apply=True, confirm=False, client=None)
checks = [
    plan["would_download"] is False,
    plan["would_cut"] is False,
    plan["would_upload"] is False,
    plan["would_post_video"] is False,
    blocked["status"] == "BLOCKED",
    "--apply requires --confirm-production-media" in blocked["blocked_reasons"],
    any("ALLOW_VIDEO_DOWNLOAD=true required" == r for r in blocked["blocked_reasons"]),
]

good_text = "配信で伸び悩んだ時は、話題を増やすより初見の人が入りやすい空気を整える方が先。入室へのお礼、今話している内容、気軽にコメントできる一言。この3つだけでも滞在しやすさは変わる。"
source_videos = [
    {
        "source_video_id": "sv_tt",
        "platform": "tiktok",
        "canonical_video_url": "https://www.tiktok.com/@creator/video/1234567890123456789",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
    },
    {
        "source_video_id": "sv_yt",
        "platform": "youtube",
        "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
    },
]
clips = [
    {"clip_candidate_id": "clip_tt", "source_video_id": "sv_tt", "clip_status": "AUTO_APPROVED", "public_post_text": good_text, "clip_score": 99, "transcript_grounded": "true", "alignment_status": "PASS"},
    {"clip_candidate_id": "clip_yt_1", "source_video_id": "sv_yt", "clip_status": "AUTO_APPROVED", "public_post_text": good_text, "clip_score": 90, "transcript_grounded": "true", "alignment_status": "PASS"},
    {"clip_candidate_id": "clip_yt_2", "source_video_id": "sv_yt", "clip_status": "AUTO_APPROVED", "public_post_text": good_text, "clip_score": 89, "transcript_grounded": "true", "alignment_status": "PASS"},
]
selected, selected_video, _ = select_candidate(clips, source_videos, [])
checks.extend([
    selected["clip_candidate_id"] == "clip_tt",
    selected_video["source_video_id"] == "sv_tt",
    is_real_discovered_video({"discovery_status": "PLANNED_ONLY", "platform": "youtube", "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk"}) is False,
])
next_selected, _, _ = select_candidate(clips, source_videos, [{"clip_candidate_id": "clip_tt"}])
checks.append(next_selected["clip_candidate_id"] == "clip_yt_1")
print(f"PASS: {sum(checks)} / FAIL: {len(checks)-sum(checks)}")
raise SystemExit(0 if all(checks) else 1)
