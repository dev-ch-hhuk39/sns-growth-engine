#!/usr/bin/env python3
"""Vision main claims are part of Direct source-suitability evidence."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import run_direct_reference_media_pipeline as pipeline  # noqa: E402


POST = {
    "source_post_id": "beauty_claims",
    "source_id": "src_beauty",
    "target_account_id": "beauty_account",
    "original_post_text": "メイク前の肌は、スキンケアと保湿の順番を整えると仕上がりを確認しやすい。",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
}
MEDIA = {
    "source_post_media_id": "spm_beauty_claims",
    "media_asset_id": "ma_beauty_claims",
    "media_type": "video",
    "storage_url": "https://res.cloudinary.com/demo/beauty.mp4",
    "duration_seconds": "20",
    "media_understanding": {
        "status": "PASS",
        "visual_summary": "女性が鏡の前で手順を見せる映像",
        "visible_text": "",
        "main_claims_json": '["メイク前に肌を保湿する", "スキンケアの順番を整える"]',
    },
}


class CaptionService:
    called = False

    def generate(self, *_args, **_kwargs):
        self.called = True
        return {
            "status": "BLOCKED",
            "public_post_text": "",
            "blocked_reasons": ["fixture_stop_after_suitability"],
            "semantic_alignment": {"status": "BLOCKED"},
        }


service = CaptionService()
original_records = pipeline._records
original_candidates = pipeline.select_direct_candidates
try:
    pipeline._records = lambda _client, _logical: []
    pipeline.select_direct_candidates = lambda _client, _account: ([
        (POST, {**MEDIA, "carousel_media": [MEDIA]}, {}),
    ], [])
    plan = pipeline.build_plan(
        "beauty_account",
        "beauty_direct_media_review",
        object(),
        apply=False,
        caption_service=service,
    )
finally:
    pipeline._records = original_records
    pipeline.select_direct_candidates = original_candidates

attempt = plan.get("skipped_candidate_attempts", [{}])[0]
assert service.called is True
assert "direct_media_account_evidence_insufficient" not in attempt.get("blocked_reasons", [])
print("PASS test_direct_media_uses_understanding_claims.py")
