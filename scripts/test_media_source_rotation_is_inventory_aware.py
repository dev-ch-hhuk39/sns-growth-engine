#!/usr/bin/env python3
"""Discovery and clip selection do not hard-code one source or platform."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from discover_approved_source_videos import order_sources_for_discovery
from run_media_production_pipeline import select_candidate

sources = [
    {"source_id": "src_a"},
    {"source_id": "src_b"},
]
ordered = order_sources_for_discovery(sources, [
    {"source_id": "src_a", "last_seen_at": "2026-07-19T00:00:00Z"},
    {"source_id": "src_a", "last_seen_at": "2026-07-19T01:00:00Z"},
])

good = "配信を始める時は、初見がコメントしやすい入口を用意すると会話が続きやすい。\n\n今の話題を短く伝え、答えやすい質問を一つ置く。\n\n大きな企画より、参加しやすい空気を丁寧に作ることが大事。"
videos = [
    {"source_video_id": "sv_yt", "source_id": "src_a", "platform": "youtube", "account_id": "liver_manager", "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk", "rights_status": "approved_creator_clip", "permission_status": "approved"},
    {"source_video_id": "sv_tt", "source_id": "src_b", "platform": "tiktok", "account_id": "liver_manager", "canonical_video_url": "https://www.tiktok.com/@creator/video/7123456789012345678", "rights_status": "approved_creator_clip", "permission_status": "approved"},
]
clips = [
    {"clip_candidate_id": "clip_yt", "clip_id": "clip_yt", "source_video_id": "sv_yt", "account_id": "liver_manager", "clip_status": "READY", "transcript_grounded": "true", "alignment_status": "PASS", "public_post_text": good, "clip_score": 99, "rights_status": "approved_creator_clip", "permission_status": "approved"},
    {"clip_candidate_id": "clip_tt", "clip_id": "clip_tt", "source_video_id": "sv_tt", "account_id": "liver_manager", "clip_status": "READY", "transcript_grounded": "true", "alignment_status": "PASS", "public_post_text": good, "clip_score": 80, "rights_status": "approved_creator_clip", "permission_status": "approved"},
]
posted = [{"account_id": "liver_manager", "status": "POSTED", "source_video_id": "sv_yt", "clip_candidate_id": "old"}]
selected, video, _reasons = select_candidate(clips, videos, posted, "liver_manager")
checks = {
    "source with less inventory discovered first": ordered[0]["source_id"] == "src_b",
    "less-used platform/source beats fixed YouTube priority": selected and selected["clip_candidate_id"] == "clip_tt",
    "selected source retained": video and video["source_id"] == "src_b",
}
for label, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'} {label}")
raise SystemExit(0 if all(checks.values()) else 1)
