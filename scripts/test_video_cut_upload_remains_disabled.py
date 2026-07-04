#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    cfg = json.loads((ROOT / "config/autonomous_mode.json").read_text(encoding="utf-8"))
    ok = cfg.get("allow_video_download") is False and cfg.get("allow_video_cut") is False and cfg.get("allow_cloudinary_upload") is False and cfg.get("allow_transcription_api") is False
    print(f"  {'PASS' if ok else 'FAIL'} video cut/upload remains disabled")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
