#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from discover_approved_source_videos import (  # noqa: E402
    is_persistable_source_video,
    merge_video_detail_metadata,
)

placeholder = {
    "source_video_id": "sv_src_ns_yt_cand_006_abcdefghijk",
    "source_id": "src_ns_yt_cand_006",
    "account_id": "night_scout",
    "platform": "youtube",
    "video_id": "abcdefghijk",
    "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
    "original_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
    "title": "night_scout YouTube reference 06 video candidate 01",
    "discovery_status": "DISCOVERED",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
}
detail = {
    "title": "キャバ嬢が話す、お店選びで大事なこと",
    "description": "自分に合うお店の見つけ方を話す動画。",
    "duration": 74,
    "uploader_id": "ichijo_hibiki",
    "upload_date": "20260820",
}
enriched = merge_video_detail_metadata(placeholder, detail)

checks = [
    ("placeholder metadata is never persisted", not is_persistable_source_video(placeholder)),
    ("bounded detail preserves source identity", enriched["source_video_id"] == placeholder["source_video_id"]),
    ("real title replaces placeholder", enriched["title"] == detail["title"]),
    ("duration and author are enriched", enriched["duration_seconds"] == 74 and enriched["author_handle"] == "ichijo_hibiki"),
    ("verified detail is persistable", is_persistable_source_video(enriched)),
]
failed = [name for name, ok in checks if not ok]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
