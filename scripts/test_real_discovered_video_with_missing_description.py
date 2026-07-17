#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_media_growth_engine import is_real_discovered_video  # noqa: E402

real_flat_video = {
    "source_video_id": "sv_src_ns_yt_cand_001_8Xmkojfw90Q",
    "account_id": "night_scout",
    "platform": "youtube",
    "video_id": "8Xmkojfw90Q",
    "canonical_video_url": "https://www.youtube.com/watch?v=8Xmkojfw90Q",
    "title": "キャバ嬢の対談",
    "description_preview": "candidate metadata only",
    "discovery_status": "DISCOVERED",
}
planned = {**real_flat_video, "title": "reference video candidate 01", "discovery_status": "PLANNED_ONLY"}
checks = [
    ("real channel video accepted without description", is_real_discovered_video(real_flat_video)),
    ("synthetic planned row remains blocked", not is_real_discovered_video(planned)),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks)-len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
