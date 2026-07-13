#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
wf = (ROOT / ".github/workflows/media-growth-production.yml").read_text()
checks = [
    'cron: "20 22 * * *"' in wf,
    'ACCOUNT_ID: "liver_manager"' in wf,
    "confirm_production_media" in wf,
    "kill_switch" in wf,
    'ALLOW_REAL_X_POST: "false"' in wf,
    'ALLOW_TRANSCRIPTION_API: "false"' in wf,
    'ALLOW_VIDEO_DOWNLOAD: "true"' in wf,
    'ALLOW_VIDEO_CUT: "true"' in wf,
    'ALLOW_CLOUDINARY_UPLOAD: "true"' in wf,
    '--prepare-only' in wf,
    'ALLOW_REAL_THREADS_VIDEO_POST: "false"' in wf,
    "run_media_production_pipeline.py" in wf,
]
print(f"PASS: {sum(checks)} / FAIL: {len(checks)-sum(checks)}")
raise SystemExit(0 if all(checks) else 1)
