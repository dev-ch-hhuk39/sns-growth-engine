#!/usr/bin/env python3
"""Clip candidates persist spoken evidence without stage-direction noise."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from media_growth_schemas import (  # noqa: E402
    build_clip_candidate_for_video,
    clean_clip_transcript_excerpt,
)


raw = "[音楽]初見が入ったら今の話題を一言で伝えると、コメントしやすくなります。【拍手】"
clean = clean_clip_transcript_excerpt(raw)
assert clean == "初見が入ったら今の話題を一言で伝えると、コメントしやすくなります。", clean

source = {
    "source_id": "source-1",
    "target_account_id": "liver_manager",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
}
video = {
    "source_video_id": "video-1",
    "account_id": "liver_manager",
    "platform": "youtube",
    "video_id": "abc",
    "canonical_video_url": "https://www.youtube.com/watch?v=abc",
    "duration_seconds": "60",
}
candidate = build_clip_candidate_for_video(
    source,
    video,
    transcript_grounded=True,
    transcript_signal_count=1,
    transcript_excerpt=raw,
    start_seconds=5,
    end_seconds=25,
)
assert "[音楽]" not in candidate["transcript_excerpt"], candidate
assert "【拍手】" not in candidate["transcript_excerpt"], candidate
assert "初見" in candidate["transcript_excerpt"], candidate

print("PASS test_clip_transcript_noise_removed_before_queue.py")
