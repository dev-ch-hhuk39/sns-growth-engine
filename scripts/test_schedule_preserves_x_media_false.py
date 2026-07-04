#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLAGS = ['ALLOW_REAL_X_POST: "false"', 'ALLOW_VIDEO_DOWNLOAD: "false"', 'ALLOW_VIDEO_CUT: "false"', 'ALLOW_CLOUDINARY_UPLOAD: "false"', 'ALLOW_TRANSCRIPTION_API: "false"']


def main() -> int:
    texts = [(ROOT / f".github/workflows/{name}").read_text(encoding="utf-8") for name in ("autonomous-growth-loop-night-scout.yml", "autonomous-growth-loop-liver-manager.yml")]
    ok = all(all(flag in text for flag in FLAGS) for text in texts)
    print(f"  {'PASS' if ok else 'FAIL'} schedule preserves x/media false")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
