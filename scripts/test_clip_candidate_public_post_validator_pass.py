#!/usr/bin/env python3
from run_media_growth_engine import build_media_growth_plan
from media_growth_test_fixtures import liver_video_and_transcript

def main() -> int:
    video, transcript = liver_video_and_transcript()
    p = build_media_growth_plan("liver_manager", existing_source_videos=[video], existing_transcripts=[transcript])
    ok = p["top_clip_candidates"] and all(c["public_post_validator_status"] == "PASS" for c in p["top_clip_candidates"])
    print(f"  {'PASS' if ok else 'FAIL'} clip candidate public post validator pass")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
