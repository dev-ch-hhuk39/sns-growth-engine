#!/usr/bin/env python3
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_media_growth_engine import build_media_growth_plan  # noqa: E402
from media_growth_test_fixtures import fixture_caption_service  # noqa: E402

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
    "comments_json": json.dumps([
        {"text": "配信で初見のコメントが伸びない理由が分かりました"},
        {"text": "リスナーへの話題の伝え方を変えてみます"},
        {"text": "初見への声かけで大事なポイントを確認できました"},
        {"text": "配信で初見のコメントが伸びない理由は、リスナーが不安になる失敗を避けることが大事です。"},
    ], ensure_ascii=False),
}
without_transcript = build_media_growth_plan(
    "liver_manager",
    existing_source_videos=[video],
    existing_transcripts=[],
    caption_service=fixture_caption_service(),
)
transcript = {
    "transcript_id": f"tr_{video['source_video_id']}",
    "source_video_id": video["source_video_id"],
    "transcription_status": "DONE",
    "transcript_text": "配信で初見のコメントが伸びない理由は、リスナーが不安になる失敗を避けることが大事です。まず今の話題を確認し、伝え方を変えるポイントを選ぶためです。",
    "segments_json": json.dumps([
        {"start": 1, "end": 16, "text": "配信で初見のコメントが伸びない理由は、リスナーが不安になる失敗を避けることが大事です。"},
        {"start": 18, "end": 34, "text": "まず今の話題を確認し、伝え方を変えるポイントを選ぶためです。"},
    ], ensure_ascii=False),
}
with_transcript = build_media_growth_plan(
    "liver_manager",
    existing_source_videos=[video],
    existing_transcripts=[transcript],
    caption_service=fixture_caption_service(),
)
first = with_transcript["top_clip_candidates"][0] if with_transcript["top_clip_candidates"] else {}
checks = [
    ("no transcript creates no ready clips", without_transcript["clip_candidate_count"] == 0),
    ("transcript creates clips", with_transcript["clip_candidate_count"] > 0),
    ("clip is transcript grounded", first.get("transcript_grounded") is True),
    ("clip has transcript id", first.get("transcript_id") == transcript["transcript_id"]),
    ("clip auto approved only when grounded", first.get("clip_status") == "READY"),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
