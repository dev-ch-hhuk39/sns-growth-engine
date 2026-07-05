#!/usr/bin/env python3
import json
from pathlib import Path
from media_growth_schemas import build_clip_candidate_for_video, build_source_video

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    src = next(s for s in json.loads((ROOT / "config/source_accounts/default_sources.json").read_text())["sources"] if s["source_id"] == "src_lm_yt_user_001")
    video = build_source_video(src, 2)
    clip = build_clip_candidate_for_video(src, video, 1)
    ok = clip["source_video_id"] == video["source_video_id"] and clip["video_id"] == video["video_id"]
    print(f"  {'PASS' if ok else 'FAIL'} clip candidate includes source_video_id")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
