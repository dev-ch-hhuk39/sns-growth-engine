#!/usr/bin/env python3
from argparse import Namespace

from download_approved_media import build_download_plan
from transcribe_approved_source_videos import attach_approved_storage_inputs, eligible_videos

canonical = "https://www.tiktok.com/@creator/video/7661997892839804178"
video = {
    "source_video_id": "sv_real",
    "account_id": "liver_manager",
    "platform": "tiktok",
    "canonical_video_url": canonical,
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "discovery_status": "REAL_DISCOVERY",
}
asset = {
    "media_id": "ma_existing",
    "account_id": "liver_manager",
    "source_post_url": canonical,
    "storage_url": "https://res.cloudinary.com/example/video/upload/approved.mp4",
    "upload_status": "UPLOADED",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
}
enriched = attach_approved_storage_inputs([video], [asset])
selected, _ = eligible_videos(enriched, [], account_id="liver_manager", limit=1)
args = Namespace(
    source_video_id="sv_real",
    source_video_row=enriched[0],
    source_videos_json="",
    source_url="",
    rights_status="",
    download=False,
    confirm_download=False,
    dry_run=True,
)
plan = build_download_plan(args)
checks = [
    ("approved asset attached", enriched[0]["approved_storage_media_asset_id"] == "ma_existing"),
    ("approved asset prioritized", selected[0]["source_video_id"] == "sv_real"),
    ("download reuses cloudinary URL", plan["source_url"] == asset["storage_url"]),
    ("canonical individual video still required", "individual_video_url_required" not in plan["blocked_reasons"]),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
