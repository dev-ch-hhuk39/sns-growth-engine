#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import run_media_growth_engine as growth


class BlockedCaptionService:
    def generate(self, *args, **kwargs):
        del args, kwargs
        return {
            "status": "BLOCKED",
            "public_post_text": "",
            "blocked_reasons": [
                "fixture_primary_blocked"
            ],
            "semantic_alignment": {
                "status": "BLOCKED",
                "blocked_reasons": [
                    "fixture_alignment_blocked"
                ],
            },
        }


video = {
    "source_video_id": (
        "sv_src_lm_yt_user_001_abcdefghijk"
    ),
    "source_id": "src_lm_yt_user_001",
    "account_id": "liver_manager",
    "platform": "youtube",
    "source_type": "channel",
    "source_url": (
        "https://youtube.com/channel/"
        "UCzFzty7aEd4tw3NqCW6pkLQ"
    ),
    "video_id": "abcdefghijk",
    "canonical_video_url": (
        "https://www.youtube.com/watch"
        "?v=abcdefghijk"
    ),
    "title": "配信初心者向け",
    "duration_seconds": 80,
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "discovery_status": "DISCOVERED",
}

part_1 = {
    "transcript_id": (
        f"tr_{video['source_video_id']}_part_001"
    ),
    "source_video_id": video["source_video_id"],
    "transcription_status": (
        "YOUTUBE_CAPTIONS_DONE"
    ),
    "transcript_text": (
        "配信で初見のコメントを増やすには、"
        "今の話題を短く伝えます。"
    ),
    "segments_json": json.dumps([
        {
            "start": 1,
            "end": 21,
            "text": (
                "配信で初見のコメントを"
                "増やすには、今の話題を"
                "短く伝えます。"
            ),
        },
    ], ensure_ascii=False),
    "transcription_scope": (
        "youtube_caption_chunk:1/2"
    ),
}

part_2 = {
    "transcript_id": (
        f"tr_{video['source_video_id']}_part_002"
    ),
    "source_video_id": video["source_video_id"],
    "transcription_status": (
        "YOUTUBE_CAPTIONS_DONE"
    ),
    "transcript_text": (
        "リスナーが入りやすいように、"
        "コメントへ答える余白を作ります。"
    ),
    "segments_json": json.dumps([
        {
            "start": 23,
            "end": 45,
            "text": (
                "リスナーが入りやすいように、"
                "コメントへ答える余白を"
                "作ります。"
            ),
        },
    ], ensure_ascii=False),
    "transcription_scope": (
        "youtube_caption_chunk:2/2"
    ),
}

merged = growth._merge_transcript_rows(
    [part_1, part_2]
)
single = growth._merge_transcript_rows(
    [part_1]
)

plan = growth.build_media_growth_plan(
    "liver_manager",
    existing_source_videos=[video],
    existing_transcripts=[part_1, part_2],
    caption_service=BlockedCaptionService(),
    allow_source_copyedit_fallback=True,
)

top = (
    plan["top_clip_candidates"][0]
    if plan["top_clip_candidates"]
    else {}
)

night_policy = growth.night_subject_policy_check(
    {
        "target_account_ids": [
            "night_scout"
        ],
    },
    {
        "title": (
            "キャバクラで働く女優に"
            "トップの条件を聞く"
        ),
    },
)

checks = [
    (
        "chunked transcript rows merge",
        len(
            growth._segments(
                merged[video["source_video_id"]]
            )
        )
        == 2,
    ),
    (
        "single transcript id is preserved",
        single[video["source_video_id"]][
            "transcript_id"
        ]
        == part_1["transcript_id"],
    ),
    (
        "copyedit fallback creates candidate",
        plan["clip_candidate_count"] > 0,
    ),
    (
        "copyedit fallback provider recorded",
        top.get("caption_provider")
        == "deterministic_source_copyedit",
    ),
    (
        "copyedit public validator passes",
        top.get(
            "public_post_validator_status"
        )
        == "PASS",
    ),
    (
        "copyedit semantic alignment passes",
        top.get("alignment_status")
        == "PASS",
    ),
    (
        "night female metadata cue passes",
        night_policy["status"] == "PASS",
    ),
]

failed = [
    name
    for name, passed in checks
    if not passed
]
for name, passed in checks:
    print(
        f"  {'PASS' if passed else 'FAIL'} "
        f"{name}"
    )
print(
    f"PASS: {len(checks) - len(failed)} "
    f"/ FAIL: {len(failed)}"
)
raise SystemExit(1 if failed else 0)
