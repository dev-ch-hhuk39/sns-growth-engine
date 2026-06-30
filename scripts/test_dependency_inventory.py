#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
doc = (ROOT / "docs/dependency-inventory.md").read_text(encoding="utf-8")
req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
required = ["beautifulsoup4", "lxml", "playwright", "yt-dlp", "youtube-transcript-api", "ffmpeg-python", "cloudinary", "pillow"]
checks = [
    ("inventory exists", "Dependency Inventory" in doc),
    ("columns present", all(c in doc for c in ["tool/library", "status", "current_location", "target_script", "risk / ToS note"])),
    ("agent reach row", "| Agent Reach |" in doc),
    ("cli-anything row", "| CLI-Anything |" in doc),
    ("threads scraper row", "| Threads Scraper系 |" in doc),
    ("required deps in requirements", all(d in req for d in required)),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
