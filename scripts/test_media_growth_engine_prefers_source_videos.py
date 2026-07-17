#!/usr/bin/env python3
from run_media_growth_engine import build_media_growth_plan

def main() -> int:
    p = build_media_growth_plan("liver_manager")
    ok = p["source_videos_source"] in {"existing_source_videos", "none_discover_first"} and p["source_video_count"] >= 0
    print(f"  {'PASS' if ok else 'FAIL'} media growth uses only real source_videos")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
