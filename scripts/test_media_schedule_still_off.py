#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    cfg = json.loads((ROOT / "config/media_growth_engine.json").read_text())
    ok = cfg["video_post_enabled"] is False and cfg["threads_video_post_enabled"] is False and cfg["cloudinary_upload_enabled"] is False
    print(f"  {'PASS' if ok else 'FAIL'} media schedule still off")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
