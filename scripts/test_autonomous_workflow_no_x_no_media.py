#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    files = [
        ROOT / ".github/workflows/autonomous-growth-loop.yml",
        ROOT / ".github/workflows/autonomous-growth-loop-night-scout.yml",
        ROOT / ".github/workflows/autonomous-growth-loop-liver-manager.yml",
    ]
    checks = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        checks.extend([
            'ALLOW_REAL_X_POST: "false"' in text,
            'ALLOW_VIDEO_DOWNLOAD: "false"' in text,
            'ALLOW_VIDEO_CUT: "false"' in text,
            'ALLOW_CLOUDINARY_UPLOAD: "false"' in text,
            'ALLOW_TRANSCRIPTION_API: "false"' in text,
        ])
    ok = all(checks)
    print(f"  {'PASS' if ok else 'FAIL'} workflow no x no media")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
