#!/usr/bin/env python3
from media_growth_schemas import clip_count_for_video

def main() -> int:
    ok = clip_count_for_video({"duration_seconds": 18}, {"max_clip_candidates_per_video": 3}) == 1
    print(f"  {'PASS' if ok else 'FAIL'} short video generates one clip")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
