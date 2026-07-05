#!/usr/bin/env python3
from media_growth_schemas import clips_overlap

def main() -> int:
    a = {"video_id": "v", "start_seconds": 10, "end_seconds": 35}
    b = {"video_id": "v", "start_seconds": 34, "end_seconds": 50}
    ok = clips_overlap(a, b, 2)
    print(f"  {'PASS' if ok else 'FAIL'} clip candidate overlap blocked")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
