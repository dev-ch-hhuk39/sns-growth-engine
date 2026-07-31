#!/usr/bin/env python3
"""Final media captions must be regenerated from exact clip evidence."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

from run_media_production_pipeline import (
    _generate_final_media_caption,
)


GOOD_TEXT = (
    "配信で初見がすぐ抜ける時は、話題の面白さだけでなく"
    "入りやすさを見直した方がいい。\n\n"
    "入室に気づいたら、今話している内容を一言伝えて、"
    "答えやすい質問を置く。この順番を決めておくと、"
    "コメントのきっかけを作りやすい。"
)

OLD_TEXT = (
    "これは候補生成時に保存された古い本文であり、"
    "投稿時には使用してはいけません。"
)

PASS_ALIGNMENT = {
    "status": "PASS",
    "blocked_reasons": [],
    "final_alignment_score": 1,
    "main_claim_coverage": 1,
    "unsupported_claim_count": 0,
    "source_copy_similarity": 0,
    "recent_post_similarity": 0,
}


class SequenceService:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *_args, **_kwargs):
        self.calls += 1

        if self.calls == 1:
            return {
                "status": "BLOCKED",
                "public_post_text": "",
                "blocked_reasons": [
                    "first_attempt_failed",
                ],
                "provider_name": "fake",
                "provider_version": "1",
                "provider_status": "FAILED",
                "semantic_alignment": {
                    "status": "BLOCKED",
                    "blocked_reasons": [
                        "first_alignment_failed",
                    ],
                },
                "claim_support": [],
            }

        return {
            "status": "PASS",
            "public_post_text": GOOD_TEXT,
            "blocked_reasons": [],
            "provider_name": "fake",
            "provider_version": "2",
            "provider_status": "PASS",
            "semantic_alignment": PASS_ALIGNMENT,
            "claim_support": [
                {
                    "caption_claim": (
                        "初見が入りやすい順番を作る"
                    ),
                    "source_evidence": (
                        "初見への声かけと質問を置く"
                    ),
                }
            ],
        }


class AlwaysBlockedService:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *_args, **_kwargs):
        self.calls += 1

        return {
            "status": "BLOCKED",
            "public_post_text": OLD_TEXT,
            "blocked_reasons": [
                f"attempt_{self.calls}_blocked",
            ],
            "provider_name": "fake",
            "provider_version": "blocked",
            "provider_status": "FAILED",
            "semantic_alignment": {
                "status": "BLOCKED",
                "blocked_reasons": [
                    "semantic_alignment_failed",
                ],
            },
            "claim_support": [],
        }


clip = {
    "clip_candidate_id": "clip_contract",
    "source_video_id": "sv_contract",
    "account_id": "liver_manager",
    "transcript_grounded": "true",
    "transcript_excerpt": (
        "初見が来たら今の話題を短く伝えて、"
        "答えやすい質問を置くとコメントしやすくなる。"
    ),
    "start_seconds": "12",
    "end_seconds": "24",
    "public_post_text": OLD_TEXT,
}

source_video = {
    "source_video_id": "sv_contract",
    "source_id": "source_contract",
    "platform": "youtube",
    "canonical_video_url": (
        "https://www.youtube.com/watch?v=abcdefghijk"
    ),
    "title": "初見が入りやすい配信",
    "description_preview": (
        "配信初心者向けに声かけの順番を説明する"
    ),
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
}

asset = {
    "media_asset_id": "asset_contract",
    "storage_url": (
        "https://media.example.invalid/clip.mp4"
    ),
    "upload_status": "UPLOADED",
    "duration_seconds": "12",
    "aspect_ratio": "9:16",
}


sequence = SequenceService()

passed = _generate_final_media_caption(
    clip=clip,
    source_video=source_video,
    media_asset=asset,
    account_id="liver_manager",
    recent_posts=[],
    caption_service=sequence,
    max_attempts=3,
)

assert passed["status"] == "PASS", passed
assert passed["caption_attempt_count"] == 2
assert sequence.calls == 2
assert passed["public_post_text"] == GOOD_TEXT
assert passed["public_post_text"] != OLD_TEXT
assert passed["alignment_status"] == "PASS"
assert len(passed["caption_attempts"]) == 2


blocked_service = AlwaysBlockedService()

blocked = _generate_final_media_caption(
    clip=clip,
    source_video=source_video,
    media_asset=asset,
    account_id="liver_manager",
    recent_posts=[],
    caption_service=blocked_service,
    max_attempts=3,
)

assert blocked["status"] == "REVIEW_REQUIRED"
assert blocked["public_post_text"] == ""
assert blocked["caption_attempt_count"] == 3
assert blocked_service.calls == 3
assert "caption_retry_limit_reached" in (
    blocked["blocked_reasons"]
)


missing_excerpt_service = SequenceService()

missing_excerpt = _generate_final_media_caption(
    clip={
        **clip,
        "transcript_excerpt": "",
    },
    source_video=source_video,
    media_asset=asset,
    account_id="liver_manager",
    recent_posts=[],
    caption_service=missing_excerpt_service,
    max_attempts=3,
)

assert missing_excerpt["status"] == "REVIEW_REQUIRED"
assert missing_excerpt["public_post_text"] == ""
assert "transcript_excerpt_missing" in (
    missing_excerpt["blocked_reasons"]
)
assert missing_excerpt_service.calls == 0


source = (
    ROOT / "scripts/run_media_production_pipeline.py"
).read_text(encoding="utf-8")

saved_start = source.index(
    "def execute_saved_media_post("
)
execute_start = source.index(
    "\ndef execute(",
    saved_start,
)
main_start = source.index(
    "\ndef main()",
    execute_start,
)

saved_body = source[saved_start:execute_start]
execute_body = source[execute_start:main_start]

assert (
    saved_body.index(
        "_generate_final_media_caption("
    )
    < saved_body.index(
        "validation = validate_media_post({"
    )
)

assert (
    execute_body.index(
        'upload.get("status") != "UPLOADED"'
    )
    < execute_body.index(
        "_generate_final_media_caption("
    )
    < execute_body.index(
        "validation = validate_media_post({"
    )
)

assert (
    'text = str(clip.get("public_post_text")'
    not in saved_body
)

assert (
    'text = str(clip.get("public_post_text")'
    not in execute_body
)

print(
    "PASS "
    "test_final_media_caption_after_asset_ready.py"
)
