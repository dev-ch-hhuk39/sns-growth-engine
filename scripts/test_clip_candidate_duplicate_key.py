#!/usr/bin/env python3
from media_growth_schemas import duplicate_clip_key

def main() -> int:
    key = duplicate_clip_key({"platform": "tiktok", "video_id": "v", "start_seconds": 1.2, "end_seconds": 9.8})
    ok = key == "tiktok:v:1:9"
    print(f"  {'PASS' if ok else 'FAIL'} clip candidate duplicate key")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
