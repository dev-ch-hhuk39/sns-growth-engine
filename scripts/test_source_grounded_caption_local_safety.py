#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from acquisition.contracts import ProviderResult  # noqa: E402
from acquisition.models import SourcePostBundle  # noqa: E402
from generation.source_grounded_caption import (  # noqa: E402
    SourceGroundedCaptionService,
    source_fact_attribution_blockers,
)
from evidence_context_caption import transcript_claim_quality_blockers  # noqa: E402


class CaptionProvider:
    provider_name = "fixture"
    provider_version = "1"

    def generate(self, *_args, **_kwargs):
        return ProviderResult(
            self.provider_name,
            self.provider_version,
            "PASS",
            data={
                "internal_analysis": {"main_claims": ["保湿は一つずつ試す"]},
                "public_post_text": "スキンケアは一度に全部変えず、保湿を一つずつ試してみてください。",
                "claim_support": [
                    {
                        "caption_claim": "保湿は一つずつ試す",
                        "source_evidence": "保湿は一つずつ試す",
                    }
                ],
                "blocked_reasons": [],
            },
        )


class AlignmentProvider:
    def __init__(self) -> None:
        self.public_text = ""

    def evaluate(self, **kwargs):
        self.public_text = str(kwargs["public_post_text"])
        return ProviderResult("fixture_alignment", "1", "PASS", data={"status": "PASS", "blocked_reasons": []})


post = SourcePostBundle(
    source_post_id="sp_beauty_local_voice",
    source_id="src_beauty_local_voice",
    target_account_id="beauty_account",
    platform="tiktok",
    profile_url="https://www.tiktok.com/@fixture",
    canonical_post_url="https://www.tiktok.com/@fixture/video/123",
    external_post_id="123",
    original_post_text="スキンケアは一度に全部変えず、保湿は一つずつ試す。",
    published_at="",
)
alignment = AlignmentProvider()
result = SourceGroundedCaptionService(CaptionProvider(), alignment_provider=alignment).generate(
    post,
    account_id="beauty_account",
)

checks = [
    (
        "Beauty voice is normalized locally before alignment",
        "個人的には" in alignment.public_text
        and "してみてほしい" in alignment.public_text
        and "。" not in alignment.public_text,
    ),
    (
        "normalized public text is returned",
        result["public_post_text"] == alignment.public_text,
    ),
    (
        "unattributed source-owned names are blocked",
        source_fact_attribution_blockers(
            "ベッカンでは担当の数が多い。",
            "ベッカンでは担当の数が多い。",
        )
        == ["source_owned_fact_attribution_missing"],
    ),
    (
        "explicit source attribution is accepted",
        not source_fact_attribution_blockers(
            "ベッカンでは担当の数が多い。",
            "この動画では、ベッカンは担当の数が多いと話している。",
        ),
    ),
    (
        "garbled transcript evidence is blocked",
        "transcript_claim_corrupted"
        in transcript_claim_quality_blockers(
            "謎に変なギフトを送る人の気持ちとは=謎に変なギフトBICZETECT"
        ),
    ),
    (
        "truncated transcript evidence is blocked",
        "transcript_claim_truncated"
        in transcript_claim_quality_blockers(
            "ライバー同士が初対面で関係性がまだできていないとい"
        ),
    ),
]

for name, passed in checks:
    print(f"  {'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if all(passed for _, passed in checks) else 1)
