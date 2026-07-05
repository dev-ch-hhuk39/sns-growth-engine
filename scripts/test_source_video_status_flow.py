#!/usr/bin/env python3
from media_growth_schemas import SOURCE_VIDEO_STATUS_FLOW

def main() -> int:
    needed = ["DISCOVERED", "CLIP_CANDIDATES_READY", "DOWNLOADED", "CUT", "UPLOADED", "POSTED", "BLOCKED"]
    ok = all(x in SOURCE_VIDEO_STATUS_FLOW for x in needed)
    print(f"  {'PASS' if ok else 'FAIL'} source video status flow")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
