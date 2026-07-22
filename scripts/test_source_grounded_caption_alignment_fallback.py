#!/usr/bin/env python3
"""A malformed model claim-support response retries the strict grounded fallback."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.contracts import ProviderResult
from acquisition.models import SourcePostBundle
from generation.source_grounded_caption import SourceGroundedCaptionService


class WeakClaimProvider:
    provider_name = "weak_fixture"
    provider_version = "1"

    def generate(self, *_args, **_kwargs):
        return ProviderResult(self.provider_name, self.provider_version, "PASS", data={
            "internal_analysis": {"main_claims": ["根拠のない主張"]},
            "public_post_text": "配信を始める時は、まず初見さんが入りやすい空気を作ることが大切です。",
            "claim_support": [{"caption_claim": "根拠のない主張", "source_evidence": "存在しない根拠"}],
            "blocked_reasons": [],
        })


post = SourcePostBundle(
    source_post_id="sp_1", source_id="source_1", target_account_id="liver_manager", platform="tiktok",
    profile_url="https://www.tiktok.com/@allowed", canonical_post_url="https://www.tiktok.com/@allowed/video/1",
    external_post_id="1", original_post_text="配信では初見さんが入りやすい空気を作ることが大切です。",
    published_at="",
)
result = SourceGroundedCaptionService(WeakClaimProvider(), allow_deterministic_fallback=True).generate(
    post, account_id="liver_manager"
)
assert result["status"] == "PASS", result
assert result["provider_name"] == "deterministic_grounded_fallback", result
assert result["semantic_alignment"]["status"] == "PASS", result
print("PASS test_source_grounded_caption_alignment_fallback.py")
