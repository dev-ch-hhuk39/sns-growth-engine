#!/usr/bin/env python3
"""A source-grounding block retries the same provider once before fallback."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.contracts import ProviderResult
from acquisition.models import SourcePostBundle
from generation.source_grounded_caption import SourceGroundedCaptionService


class RetryProvider:
    provider_name = "retry_fixture"
    provider_version = "1"

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, *_args, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return ProviderResult(self.provider_name, self.provider_version, "PASS", data={
                "internal_analysis": {"main_claims": ["根拠のない主張"]},
                "public_post_text": "配信を始める時は、初見さんへの声かけを意識すると安心です。",
                "claim_support": [{"caption_claim": "根拠のない主張", "source_evidence": "存在しない根拠"}],
                "blocked_reasons": [],
            })
        return ProviderResult(self.provider_name, self.provider_version, "PASS", data={
            "internal_analysis": {"main_claims": ["常連だけの会話は初見が参加しづらい"]},
            "public_post_text": "配信に初見さんが来ても、常連だけの会話が続くと入りづらさを感じやすい。\n\n最初に今の話題を一言伝えて、参加のきっかけを作ってみてください。",
            "claim_support": [{"caption_claim": "常連だけの会話が続くと入りづらい", "source_evidence": "常連だけで会話していると参加しづらい"}],
            "blocked_reasons": [],
        })


provider = RetryProvider()
post = SourcePostBundle(
    source_post_id="sp_retry", source_id="source_retry", target_account_id="liver_manager", platform="threads",
    profile_url="https://www.threads.com/@allowed", canonical_post_url="https://www.threads.com/@allowed/post/retry",
    external_post_id="retry", original_post_text="配信に初見が入っても、常連だけで会話していると参加しづらい。", published_at="",
)
result = SourceGroundedCaptionService(provider).generate(post, account_id="liver_manager")
checks = [
    ("primary provider retried once", provider.calls == 2 and result.get("primary_attempt_count") == 2),
    ("retry uses unchanged alignment thresholds", result["status"] == "PASS" and result["semantic_alignment"]["status"] == "PASS"),
    ("retry text remains public only", "source" not in result["public_post_text"].lower()),
]
for name, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
raise SystemExit(0 if all(ok for _, ok in checks) else 1)
