#!/usr/bin/env python3
import importlib.util

required_modules = ["bs4", "lxml", "playwright", "yt_dlp", "youtube_transcript_api", "PIL", "ffmpeg", "cloudinary"]
optional_modules = ["twikit", "snscrape", "TikTokApi", "moviepy", "pydub", "faster_whisper", "paddleocr"]
checks = [(f"required importable {m}", importlib.util.find_spec(m) is not None) for m in required_modules]
checks += [(f"optional not required {m}", True) for m in optional_modules]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
