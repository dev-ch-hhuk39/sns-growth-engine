#!/usr/bin/env python3
from download_approved_media import is_individual_video_url

def main() -> int:
    ok = is_individual_video_url("https://www.youtube.com/watch?v=abc") and is_individual_video_url("https://www.tiktok.com/@u/video/123") and not is_individual_video_url("https://www.tiktok.com/@u")
    print(f"  {'PASS' if ok else 'FAIL'} individual video URL required for download")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
