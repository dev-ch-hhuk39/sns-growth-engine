#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "scripts/collect_video_references.py").read_text(encoding="utf-8")
checks = [
    ("yt-dlp function", "def fetch_ytdlp_metadata" in src),
    ("skip download option", '"skip_download": True' in src),
    ("download false call", "download=False" in src),
    ("status reported", "yt_dlp" in src and "adapter_status" in src),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
