#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import run_media_production_pipeline as production


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


excerpt = (
    "配信で初見のコメントを増やすには、"
    "リスナーへ今の話題を短く伝えて、"
    "答えやすい余白を作ります。"
)

video = {
    "source_video_id": "sv_1",
    "source_id": "src_1",
    "account_id": "liver_manager",
    "platform": "youtube",
    "video_id": "abcdefghijk",
    "canonical_video_url": (
        "https://www.youtube.com/watch"
        "?v=abcdefghijk"
    ),
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
}

clip = {
    "clip_candidate_id": "clip_1",
    "source_video_id": "sv_1",
    "account_id": "liver_manager",
    "clip_status": "WAITING_REVIEW",
    "reviewer_status": "WAITING_REVIEW",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
    "transcript_grounded": "true",
    "transcript_excerpt": excerpt,
    "start_seconds": "10",
    "end_seconds": "35",
    "public_post_validator_status": "PASS",
    "alignment_status": "PASS",
    "clip_score": 60,
}

normal, _, _ = production.select_candidate(
    [clip],
    [video],
    [],
    "liver_manager",
)

prepare, _, _ = production.select_candidate(
    [clip],
    [video],
    [],
    "liver_manager",
    allow_waiting_review=True,
)

blocked_without_opt_in = (
    production._generate_final_media_caption(
        clip=clip,
        source_video=video,
        media_asset={
            "media_asset_id": "ma_blocked",
            "duration_seconds": "25",
            "width": "1080",
            "height": "1920",
        },
        account_id="liver_manager",
        recent_posts=[],
        caption_service=BlockedCaptionService(),
        max_attempts=1,
    )
)

caption = production._generate_final_media_caption(
    clip=clip,
    source_video=video,
    media_asset={
        "media_asset_id": "ma_1",
        "duration_seconds": "25",
        "width": "1080",
        "height": "1920",
    },
    account_id="liver_manager",
    recent_posts=[],
    caption_service=BlockedCaptionService(),
    max_attempts=1,
    allow_source_copyedit_fallback=True,
)

checks = [
    (
        "injected service remains fail closed",
        blocked_without_opt_in["status"]
        == "REVIEW_REQUIRED",
    ),
    (
        "normal path still requires READY",
        normal is None,
    ),
    (
        "prepare-only can select reviewed evidence",
        prepare is not None
        and prepare["clip_candidate_id"]
        == "clip_1",
    ),
    (
        "final caption copyedit fallback passes",
        caption["status"] == "PASS",
    ),
    (
        "final caption provider is source copyedit",
        caption["caption_provider"]
        == "deterministic_source_copyedit",
    ),
    (
        "final caption remains source grounded",
        caption["alignment_status"] == "PASS"
        and caption[
            "unsupported_claim_count"
        ]
        == 0,
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
