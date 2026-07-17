#!/usr/bin/env python3
"""Prepared clip assets are never rebuilt; the next eligible clip is selected."""
from __future__ import annotations

from run_media_production_pipeline import select_candidate


def main() -> int:
    public_text = (
        "配信を始めたばかりの時は、話題を増やすより初見の人が入りやすい空気を整える方が大切。"
        "入室へのお礼と今話している内容を伝えるだけでも、コメントのきっかけは作りやすくなる。"
    )
    videos = [{
        "source_video_id": "sv_1",
        "account_id": "liver_manager",
        "platform": "youtube",
        "canonical_video_url": "https://www.youtube.com/watch?v=abcdefghijk",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
    }]
    clips = [
        {
            "clip_candidate_id": "clip_01",
            "source_video_id": "sv_1",
            "account_id": "liver_manager",
            "clip_status": "READY",
            "transcript_grounded": "true",
            "public_post_text": public_text,
            "clip_score": 95,
        },
        {
            "clip_candidate_id": "clip_02",
            "source_video_id": "sv_1",
            "account_id": "liver_manager",
            "clip_status": "READY",
            "transcript_grounded": "true",
            "public_post_text": public_text,
            "clip_score": 90,
        },
    ]
    assets = [{
        "media_id": "ma_clip_01",
        "video_clip_id": "clip_01",
        "account_id": "liver_manager",
        "upload_status": "UPLOADED",
        "storage_url": "https://media.example.invalid/clip_01.mp4",
    }]
    selected, _, reasons = select_candidate(clips, videos, [], "liver_manager", assets)

    clip_with_persisted_state = {
        **clips[0],
        "cut_status": "DONE",
        "upload_status": "UPLOADED",
        "media_asset_id": "ma_clip_01",
    }
    persisted_selected, _, persisted_reasons = select_candidate(
        [clip_with_persisted_state, clips[1]], videos, [], "liver_manager", [],
    )
    checks = [
        ("existing media asset skips first clip", selected and selected["clip_candidate_id"] == "clip_02"),
        ("skip reason is observable", any(reason == "clip_01:already_prepared" for reason in reasons)),
        ("persisted clip state also skips first clip", persisted_selected and persisted_selected["clip_candidate_id"] == "clip_02"),
        ("persisted-state reason is observable", any(reason == "clip_01:already_prepared" for reason in persisted_reasons)),
        ("no duplicate media asset selected", selected and selected["clip_candidate_id"] != "clip_01"),
    ]
    for name, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'} {name}")
    failed = [name for name, passed in checks if not passed]
    print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
