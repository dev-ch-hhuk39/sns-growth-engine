#!/usr/bin/env python3
from media_growth_schemas import is_duplicate_source_video

def main() -> int:
    a = {"platform": "youtube", "source_id": "s", "video_id": "", "canonical_video_url": "https://youtu.be/abc123"}
    b = {"platform": "youtube", "source_id": "s", "video_id": "", "canonical_video_url": "https://www.youtube.com/watch?v=abc123&x=1"}
    ok = is_duplicate_source_video(a, [b])
    print(f"  {'PASS' if ok else 'FAIL'} discover dedupes by canonical_video_url")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
