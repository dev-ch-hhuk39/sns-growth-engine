#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_media_production_pipeline import select_candidate  # noqa: E402

text = "配信で伸び悩んだ時は、まず初見の人が入りやすい空気を整えること。入室へのお礼、今話している内容、気軽にコメントできる一言。この3つだけでも滞在しやすさは変わる。"
source_videos = [{
    "source_video_id": "sv_1",
    "platform": "youtube",
    "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
}]
ungrounded = [{
    "clip_candidate_id": "clip_1",
    "source_video_id": "sv_1",
    "clip_status": "READY",
    "public_post_text": text,
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "clip_score": 99,
    "transcript_grounded": "false",
}]
grounded = [{**ungrounded[0], "clip_candidate_id": "clip_2", "transcript_grounded": "true"}]
blocked, _, reasons = select_candidate(ungrounded, source_videos, [])
selected, _, _ = select_candidate(grounded, source_videos, [])
checks = [
    ("ungrounded clip blocked", blocked is None and any("transcript_grounding_required" in r for r in reasons)),
    ("grounded clip selected", selected and selected["clip_candidate_id"] == "clip_2"),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
