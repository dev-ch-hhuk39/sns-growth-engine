#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github/workflows/media-growth-production-night-scout.yml").read_text(encoding="utf-8")
checks = [
    ("production remains dispatch-only before canaries", 'schedule:' not in workflow and "Canary gate" in workflow),
    ("account is fixed", 'ACCOUNT_ID: "night_scout"' in workflow),
    ("workflow discovers, transcribes, and generates candidates", all(value in workflow for value in ("discover_approved_source_videos.py", "transcribe_approved_source_videos.py", "run_media_growth_engine.py"))),
    ("preparation gates are scoped", all(value in workflow for value in ('ALLOW_VIDEO_DOWNLOAD: "true"', 'ALLOW_VIDEO_CUT: "true"', 'ALLOW_CLOUDINARY_UPLOAD: "true"', '--prepare-only', 'ALLOW_MEDIA_POSTS: "false"', 'ALLOW_REAL_THREADS_VIDEO_POST: "false"'))),
    ("x and transcription api stay disabled", 'ALLOW_REAL_X_POST: "false"' in workflow and 'ALLOW_TRANSCRIPTION_API: "false"' in workflow),
    ("ffmpeg is installed before verification", "apt-get install --yes --no-install-recommends ffmpeg" in workflow),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
