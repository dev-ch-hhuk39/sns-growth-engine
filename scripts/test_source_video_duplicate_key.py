#!/usr/bin/env python3
from media_growth_schemas import source_video_duplicate_key

def main() -> int:
    key = source_video_duplicate_key({"platform": "youtube", "source_id": "s", "video_id": "v1", "canonical_video_url": "u"})
    ok = key == "youtube:s:video_id:v1"
    print(f"  {'PASS' if ok else 'FAIL'} source video duplicate key")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
