#!/usr/bin/env python3
from transcribe_approved_source_videos import eligible_videos


def video(source_video_id: str, url: str, status: str) -> dict:
    return {
        "source_video_id": source_video_id,
        "account_id": "liver_manager",
        "platform": "youtube" if "youtube" in url else "tiktok",
        "canonical_video_url": url,
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "discovery_status": status,
    }


rows = [
    video("planned_old", "https://www.youtube.com/watch?v=abcdefghijk", "DISCOVERED"),
    video("real_new", "https://www.tiktok.com/@creator/video/7662652624092597522", "REAL_DISCOVERY"),
]
selected, skipped = eligible_videos(rows, [], account_id="liver_manager", limit=1)
checks = [
    ("one selected", len(selected) == 1),
    ("real discovery first", selected[0]["source_video_id"] == "real_new"),
    ("eligible rows not skipped", not skipped),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
