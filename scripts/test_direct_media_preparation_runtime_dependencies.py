#!/usr/bin/env python3
"""The hosted direct-media plan must install every command it verifies."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
workflow = (ROOT / ".github" / "workflows" / "direct-media-preparation.yml").read_text(encoding="utf-8")
checks = {
    "ffmpeg installed": "ffmpeg tesseract-ocr tesseract-ocr-jpn" in workflow,
    "ffmpeg verified": "command -v ffmpeg" in workflow,
    "ffprobe verified": "command -v ffprobe" in workflow,
    "tesseract verified": "command -v tesseract" in workflow,
    "default posting remains disabled": 'PUBLISH_ENABLED: "false"' in workflow and 'ALLOW_REAL_THREADS_POST: "false"' in workflow,
    "apply remains explicitly confirmed": "confirm_preparation" in workflow and "--confirm-direct-media" in workflow,
}
for name, ok in checks.items():
    print(f"{'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
