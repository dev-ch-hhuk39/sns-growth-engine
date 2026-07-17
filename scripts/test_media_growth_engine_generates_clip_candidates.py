#!/usr/bin/env python3
import json
from run_media_growth_engine import build_media_growth_plan

def main() -> int:
    video = {"source_video_id": "sv_src_lm_yt_user_001_abcdefghijk", "source_id": "src_lm_yt_user_001",
             "account_id": "liver_manager", "platform": "youtube", "source_type": "channel",
             "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk", "duration_seconds": 60,
             "rights_status": "approved_creator_clip", "permission_status": "approved", "discovery_status": "DISCOVERED", "title": "real metadata"}
    transcript = {"source_video_id": video["source_video_id"], "transcription_status": "DONE", "transcript_text": "初見が入りやすい配信では挨拶と話題共有が大切です。",
                  "segments_json": json.dumps([{"start": 1, "end": 14, "text": "初見が入りやすい配信では挨拶が大切です。"}, {"start": 20, "end": 38, "text": "今の話題を共有するとコメントしやすくなります。"}], ensure_ascii=False)}
    plan = build_media_growth_plan("liver_manager", existing_source_videos=[video], existing_transcripts=[transcript])
    ok = plan["clip_candidate_count"] > 0 and plan["top_clip_candidates"]
    print(f"  {'PASS' if ok else 'FAIL'} media growth generates clip candidates")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
