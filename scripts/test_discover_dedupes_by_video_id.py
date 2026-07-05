#!/usr/bin/env python3
import json
from pathlib import Path
from discover_approved_source_videos import build_discovery_plan
from media_growth_schemas import build_source_video

ROOT = Path(__file__).resolve().parents[1]

def main() -> int:
    src = next(s for s in json.loads((ROOT / "config/source_accounts/default_sources.json").read_text())["sources"] if s["source_id"] == "src_lm_yt_user_001")
    existing = [build_source_video(src, 1)]
    p = build_discovery_plan("liver_manager", existing_source_videos=existing)
    ok = p["duplicate_video_count"] >= 1
    print(f"  {'PASS' if ok else 'FAIL'} discover dedupes by video_id")
    print(f"PASS: {1 if ok else 0} / FAIL: {0 if ok else 1}")
    return 0 if ok else 1
if __name__ == "__main__":
    raise SystemExit(main())
