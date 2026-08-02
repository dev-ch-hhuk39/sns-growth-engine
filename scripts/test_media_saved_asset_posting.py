#!/usr/bin/env python3
"""A saved clip requires exact evidence and verified AV streams."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

from run_media_production_pipeline import (
    select_saved_media_candidate,
)


def main() -> int:
    text = (
        "配信で初見さんが入りやすい空気を作るなら、"
        "今の話題を短く伝えて、答えやすい質問を"
        "置くことが大切です。"
    )

    videos = [{
        "source_video_id": "sv1",
        "source_id": "src1",
        "account_id": "liver_manager",
        "platform": "youtube",
        "canonical_video_url": (
            "https://www.youtube.com/"
            "watch?v=abcdefghijk"
        ),
    }]

    clips = [{
        "clip_candidate_id": "clip1",
        "source_video_id": "sv1",
        "account_id": "liver_manager",
        "clip_status": "MEDIA_READY",
        "rights_status": (
            "approved_creator_clip"
        ),
        "permission_status": "approved",
        "transcript_grounded": "TRUE",
        "transcript_excerpt": text,
        "start_seconds": "10",
        "end_seconds": "30",
    }]

    assets = [{
        "media_id": "asset1",
        "video_clip_id": "clip1",
        "account_id": "liver_manager",
        "upload_status": "UPLOADED",
        "storage_url": (
            "https://media.example.invalid/"
            "asset1.mp4"
        ),
        "rights_status": (
            "approved_creator_clip"
        ),
        "permission_status": "approved",
        "width": "1080",
        "height": "1920",
        "video_stream_count": "1",
        "audio_stream_count": "1",
        "media_probe_status": "PASS",
    }]

    clip, video, asset, reasons = (
        select_saved_media_candidate(
            clips,
            videos,
            assets,
            [],
            "liver_manager",
        )
    )

    skipped_clip, _, _, skipped_reasons = (
        select_saved_media_candidate(
            clips,
            videos,
            assets,
            [{
                "clip_candidate_id": "clip1",
            }],
            "liver_manager",
        )
    )

    checks = [
        (
            "selects verified uploaded asset",
            bool(clip and video and asset),
        ),
        (
            "selected asset has no blockers",
            not reasons,
        ),
        (
            "posted clip is not reused",
            (
                skipped_clip is None
                and any(
                    "already_posted" in reason
                    for reason in skipped_reasons
                )
            ),
        ),
    ]

    failed = [
        name
        for name, ok in checks
        if not ok
    ]

    for name, ok in checks:
        print(
            f"  {'PASS' if ok else 'FAIL'} "
            f"{name}"
        )

    print(
        f"PASS: {len(checks) - len(failed)} "
        f"/ FAIL: {len(failed)}"
    )

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
