#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

from evidence_context_caption import (
    PROVIDER_NAME,
    generate_evidence_context_caption,
)
from run_media_production_pipeline import (
    _generate_final_media_caption,
)


class AlwaysBlockedService:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *_args, **_kwargs):
        self.calls += 1
        return {
            "status": "BLOCKED",
            "public_post_text": "",
            "blocked_reasons": [
                f"blocked_{self.calls}",
            ],
            "provider_name": "blocked_fixture",
            "provider_version": "1",
            "provider_status": "FAILED",
            "semantic_alignment": {
                "status": "BLOCKED",
                "blocked_reasons": [
                    "fixture_alignment_blocked"
                ],
            },
            "claim_support": [],
        }


night_excerpt = (
    "キャバ嬢が店を選ぶ時は、時給だけではなく客層や"
    "バックの条件を確認して、自分が続けられる店舗か考える。"
)
liver_excerpt = (
    "初見が入室したら今の話題を短く伝えて、答えやすい質問を置くと"
    "コメントのきっかけを作りやすい。"
)

night = generate_evidence_context_caption(
    account_id="night_scout",
    transcript_excerpt=night_excerpt,
    recent_posts=[],
)
liver = generate_evidence_context_caption(
    account_id="liver_manager",
    transcript_excerpt=liver_excerpt,
    recent_posts=[],
)
unrelated = generate_evidence_context_caption(
    account_id="night_scout",
    transcript_excerpt=(
        "朝の散歩では公園の木を見ながらゆっくり歩くと気分が変わる。"
    ),
    recent_posts=[],
)

clip = {
    "clip_candidate_id": "clip_night_contract",
    "source_video_id": "sv_night_contract",
    "account_id": "night_scout",
    "transcript_grounded": "true",
    "transcript_excerpt": night_excerpt,
    "start_seconds": "100",
    "end_seconds": "130",
}
source_video = {
    "source_video_id": "sv_night_contract",
    "source_id": "src_night_contract",
    "platform": "youtube",
    "canonical_video_url": (
        "https://www.youtube.com/watch?v=abcdefghijk"
    ),
    "title": "キャバ嬢の店選び",
    "description_preview": "時給と客層を確認する話",
    "rights_status": "approved_creator_clip",
    "permission_status": "approved",
}
asset = {
    "media_asset_id": "ma_night_contract",
    "storage_url": "https://media.example.invalid/night.mp4",
    "upload_status": "UPLOADED",
    "duration_seconds": "30",
    "aspect_ratio": "9:16",
    "video_stream_count": "1",
    "audio_stream_count": "1",
    "media_probe_status": "PASS",
}
blocked_service = AlwaysBlockedService()
final_caption = _generate_final_media_caption(
    clip=clip,
    source_video=source_video,
    media_asset=asset,
    account_id="night_scout",
    recent_posts=[],
    caption_service=blocked_service,
    max_attempts=3,
    allow_source_copyedit_fallback=False,
    allow_evidence_context_fallback=True,
)

checks = [
    (
        "night evidence-context caption passes",
        night["status"] == "PASS",
    ),
    (
        "night public and semantic contracts pass",
        night["semantic_alignment"]["status"] == "PASS"
        and night["semantic_alignment"][
            "unsupported_claim_count"
        ]
        == 0,
    ),
    (
        "liver evidence-context caption passes",
        liver["status"] == "PASS",
    ),
    (
        "unrelated transcript remains blocked",
        unrelated["status"] == "BLOCKED",
    ),
    (
        "final caption uses evidence fallback as third attempt",
        final_caption["status"] == "PASS"
        and final_caption["caption_attempt_count"] == 3
        and blocked_service.calls == 2,
    ),
    (
        "final caption provider is auditable",
        final_caption["caption_provider"] == PROVIDER_NAME,
    ),
]

failed = [name for name, passed in checks if not passed]
for name, passed in checks:
    print(f"  {'PASS' if passed else 'FAIL'} {name}")
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
