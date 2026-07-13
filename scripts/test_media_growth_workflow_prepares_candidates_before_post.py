#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
wf = (ROOT / ".github/workflows/media-growth-production.yml").read_text()

checks = [
    ("discovers videos", "discover_approved_source_videos.py" in wf and "--fetch-real" in wf),
    ("transcribes videos", "transcribe_approved_source_videos.py" in wf and "--confirm-transcribe" in wf),
    ("generates grounded candidates", "run_media_growth_engine.py" in wf and "--confirm-media-growth" in wf),
    ("prepares before media ready", wf.index("Discover approved source videos") < wf.index("Prepare one approved media asset")),
    ("transcription keeps posting disabled", 'ALLOW_REAL_THREADS_POST: "false"' in wf and 'ALLOW_MEDIA_POSTS: "false"' in wf),
    ("preparation never enables posting", '--prepare-only' in wf and 'ALLOW_REAL_THREADS_VIDEO_POST: "false"' in wf and 'ALLOW_REAL_X_POST: "false"' in wf),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
