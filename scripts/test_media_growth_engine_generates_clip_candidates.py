#!/usr/bin/env python3
import json
from run_media_growth_engine import build_media_growth_plan

def main() -> int:
    video = {"source_video_id": "sv_src_lm_yt_user_001_abcdefghijk", "source_id": "src_lm_yt_user_001",
             "account_id": "liver_manager", "platform": "youtube", "source_type": "channel",
             "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk", "duration_seconds": 60,
             "rights_status": "approved_creator_clip", "permission_status": "approved", "discovery_status": "DISCOVERED", "title": "real metadata"}
    transcript = {"source_video_id": video["source_video_id"], "transcription_status": "DONE", "transcript_text": "配信で初見が入りやすくなるには、入室時に今の話題を短く伝え、コメントしやすい質問を置くことが大事です。 リスナーが参加しやすい空気を整えると、配信の会話が続きやすくなります。",
                  "segments_json": json.dumps([{"start": 1, "end": 20, "text": "配信で初見が入りやすくなるには、入室時に今の話題を短く伝え、コメントしやすい質問を置くことが大事です。"}, {"start": 22, "end": 42, "text": "リスナーが参加しやすい空気を整えると、配信の会話が続きやすくなります。"}], ensure_ascii=False)}
    plan = build_media_growth_plan("liver_manager", existing_source_videos=[video], existing_transcripts=[transcript])
    ok = plan["clip_candidate_count"] > 0 and plan["top_clip_candidates"]
    print(f"  {'PASS' if ok else 'FAIL'} media growth generates clip candidates")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
