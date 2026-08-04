#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

from build_media_activation_review_evidence import (
    build_clip_draft,
)
from evidence_context_caption import (
    generate_evidence_context_caption,
)
from media_post_validator import (
    validate_media_post,
)
from public_post_quality import (
    final_public_post_validator,
)


excerpt = (
    "キャバ嬢が店を選ぶ時は、時給だけではなく客層や"
    "バックの条件を確認して、自分が続けられる店舗か考える。"
)

clip = {
    "clip_candidate_id": "clip_stream_dimensions",
    "source_video_id": "sv_stream_dimensions",
    "source_id": "src_stream_dimensions",
    "account_id": "night_scout",
    "transcript_grounded": "true",
    "transcript_excerpt": excerpt,
    "start_seconds": "100",
    "end_seconds": "130",
    "content_hash": "clip-content-hash",
}

source_video = {
    "source_video_id": "sv_stream_dimensions",
    "source_id": "src_stream_dimensions",
    "account_id": "night_scout",
    "platform": "youtube",
    "canonical_video_url": (
        "https://www.youtube.com/watch?v=abcdefghijk"
    ),
    "content_hash": "video-content-hash",
}

asset = {
    "media_id": "ma_stream_dimensions",
    "account_id": "night_scout",
    "video_clip_id": "clip_stream_dimensions",
    "storage_url": (
        "https://media.example.invalid/clip.mp4"
    ),
    "upload_status": "UPLOADED",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "media_type": "video",
    "duration_seconds": "30",
    "aspect_ratio": "9:16",
    "width": "1080",
    "height": "1920",
    "video_stream_count": "1",
    "audio_stream_count": "1",
    "media_probe_status": "PASS",
}

permission = {
    "permission_id": "perm_stream_dimensions",
    "source_id": "src_stream_dimensions",
    "account_id": "night_scout",
    "operation": "clip",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "evidence_reference": "contract:test",
}

captured_plan: dict[str, Any] = {}


def caption_builder(
    packet: dict[str, Any],
    recent_posts: list[str],
) -> dict[str, Any]:
    return generate_evidence_context_caption(
        account_id=packet["account_id"],
        transcript_excerpt=(
            packet["media_evidence_text"]
        ),
        recent_posts=recent_posts,
    )


def media_validator(
    plan: dict[str, Any],
) -> dict[str, Any]:
    captured_plan.update(plan)
    return validate_media_post(plan)


draft = build_clip_draft(
    account_id="night_scout",
    selection=(clip, source_video, asset),
    permission=permission,
    recent_posts=[],
    caption_builder=caption_builder,
    public_validator=final_public_post_validator,
    media_validator=media_validator,
)

checks = [
    (
        "clip media plan carries width",
        str(captured_plan.get("width"))
        == "1080",
    ),
    (
        "clip media plan carries height",
        str(captured_plan.get("height"))
        == "1920",
    ),
    (
        "complete AV evidence passes",
        draft.media_validation.get("status")
        == "PASS",
    ),
    (
        "stream evidence blocker absent",
        "media_stream_evidence_missing"
        not in draft.media_validation.get(
            "blocked_reasons",
            [],
        ),
    ),
    (
        "draft has no blockers",
        draft.blockers == [],
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
