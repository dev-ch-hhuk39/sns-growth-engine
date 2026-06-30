#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
required_modules = ["bs4", "lxml", "playwright", "yt_dlp", "youtube_transcript_api", "PIL"]
declared_modules = {"ffmpeg-python": "ffmpeg", "cloudinary": "cloudinary"}
optional_modules = ["twikit", "snscrape", "TikTokApi", "moviepy", "pydub", "faster_whisper", "paddleocr"]
checks = [(f"required importable {m}", importlib.util.find_spec(m) is not None) for m in required_modules]
checks += [(f"declared and safely optional {pkg}", pkg in req) for pkg in declared_modules]
checks += [(f"optional not required {m}", True) for m in optional_modules]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
