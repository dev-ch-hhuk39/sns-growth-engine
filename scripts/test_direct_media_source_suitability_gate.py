#!/usr/bin/env python3
"""Production Direct must reject account-fit manufactured by its caption."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import run_direct_reference_media_pipeline as pipeline  # noqa: E402


def _post(post_id: str, text: str) -> dict:
    return {
        "source_post_id": post_id,
        "source_id": "src_test",
        "target_account_id": "night_scout",
        "platform": "threads",
        "canonical_post_url": f"https://www.threads.com/@approved/post/{post_id}",
        "external_post_id": post_id,
        "original_post_text": text,
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "content_hash": f"hash_{post_id}",
    }


def _media(post_id: str, summary: str, visible_text: str) -> dict:
    item = {
        "source_post_media_id": f"spm_{post_id}",
        "source_post_id": post_id,
        "media_asset_id": f"asset_{post_id}",
        "media_index": "0",
        "media_type": "video",
        "storage_url": f"https://res.cloudinary.com/demo/{post_id}.mp4",
        "cloudinary_status": "UPLOADED",
        "duration_seconds": "20",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "media_understanding": {
            "status": "PASS",
            "visual_summary": summary,
            "visible_text": visible_text,
        },
    }
    return {**item, "carousel_media": [item]}


class NeverCalledCaptionService:
    def generate(self, *_args, **_kwargs):
        raise AssertionError("caption generation must not manufacture account fit")


original_records = pipeline._records
original_candidates = pipeline.select_direct_candidates
try:
    pipeline._records = lambda _client, _logical: []
    pipeline.select_direct_candidates = lambda _client, _account: ([
        (
            _post("off_topic", "ベッカン担当キャストにコスメ情報を聞いたよ"),
            _media("off_topic", "コスメを紹介する短い動画", "リップとチークの紹介"),
            {},
        )
    ], [])
    plan = pipeline.build_plan(
        "night_scout",
        "ns_1800_direct_media",
        object(),
        apply=False,
        caption_service=NeverCalledCaptionService(),
    )
finally:
    pipeline._records = original_records
    pipeline.select_direct_candidates = original_candidates

attempt = plan.get("skipped_candidate_attempts", [{}])[0]
checks = [
    ("off-topic source is blocked", plan.get("status") == "BLOCKED"),
    (
        "source evidence is insufficient",
        "direct_source_account_evidence_insufficient" in attempt.get("blocked_reasons", []),
    ),
    (
        "media evidence is insufficient",
        "direct_media_account_evidence_insufficient" in attempt.get("blocked_reasons", []),
    ),
    ("nothing would post", plan.get("would_post") is False),
]
for name, passed in checks:
    print(f"  {'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if all(passed for _, passed in checks) else 1)
