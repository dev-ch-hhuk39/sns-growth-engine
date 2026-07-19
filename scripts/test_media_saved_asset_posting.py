#!/usr/bin/env python3
"""An uploaded approved asset can be selected without any execution step."""
from __future__ import annotations

from run_media_production_pipeline import select_saved_media_candidate


def main() -> int:
    text = "配信を続けるには、最初から完璧に話すより初見が入りやすい空気を作る方が大事。今何の話をしているか伝えて、コメントしやすい一言を置く。この積み重ねが次も来やすい配信につながる。"
    videos = [{"source_video_id": "sv1", "account_id": "liver_manager", "platform": "youtube"}]
    clips = [{"clip_candidate_id": "clip1", "source_video_id": "sv1", "rights_status": "approved_creator_clip", "permission_status": "approved", "alignment_status": "PASS", "public_post_text": text}]
    assets = [{"media_id": "asset1", "video_clip_id": "clip1", "account_id": "liver_manager", "upload_status": "UPLOADED", "storage_url": "https://media.example.invalid/asset1.mp4", "rights_status": "approved_creator_clip", "permission_status": "approved"}]
    clip, video, asset, reasons = select_saved_media_candidate(clips, videos, assets, [], "liver_manager")
    skipped_clip, _, _, skipped_reasons = select_saved_media_candidate(clips, videos, assets, [{"clip_candidate_id": "clip1"}], "liver_manager")
    checks = [
        ("selects uploaded unused approved asset", bool(clip and video and asset)),
        ("selected asset has no execution plan", not reasons),
        ("posted clip is not reused", skipped_clip is None and any("already_posted" in reason for reason in skipped_reasons)),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {name}")
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
