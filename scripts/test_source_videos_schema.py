#!/usr/bin/env python3
from media_growth_schemas import SOURCE_VIDEO_FIELDS

def main() -> int:
    required = {"source_video_id", "video_id", "canonical_video_url", "duplicate_key", "discovery_status"}
    ok = required.issubset(set(SOURCE_VIDEO_FIELDS))
    print(f"  {'PASS' if ok else 'FAIL'} source_videos schema")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
