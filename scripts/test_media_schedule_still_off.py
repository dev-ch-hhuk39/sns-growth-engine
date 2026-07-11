#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    cfg = json.loads((ROOT / "config/media_growth_engine.json").read_text())
    workflow = (ROOT / ".github/workflows/media-growth-production.yml").read_text()
    ok = (
        cfg["video_post_enabled"] is True
        and cfg["threads_video_post_enabled"] is True
        and cfg["cloudinary_upload_enabled"] is True
        and 'ALLOW_REAL_X_POST: "false"' in workflow
        and "confirm_production_media" in workflow
    )
    print(f"  {'PASS' if ok else 'FAIL'} media schedule enabled with production gates")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
