#!/usr/bin/env python3
import subprocess, sys, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
p = subprocess.run([sys.executable, "scripts/transcribe_video_reference.py", "--account-id", "night_scout", "--video-url", "https://youtu.be/dQw4w9WgXcQ", "--fetch-youtube-transcript"], cwd=ROOT, text=True, capture_output=True)
d = json.loads(p.stdout)
checks = [
    ("plan only", d["status"] == "PLAN_ONLY"),
    ("no real transcription api", d["real_transcription_api"] is False),
    ("no download", d["download"] is False),
    ("adapter status", "youtube_transcript_api" in d["adapter_status"]),
    ("no transcript preview", all(t.get("text_preview", "") == "" for t in d.get("transcripts", []))),
]
bad = [n for n, ok in checks if not ok]
for n, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {n}")
print(f"PASS: {len(checks)-len(bad)} / FAIL: {len(bad)}")
raise SystemExit(1 if bad else 0)
