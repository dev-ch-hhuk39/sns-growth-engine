#!/usr/bin/env python3
"""Accept faithful copyedits and fall back only when the caption drifts."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT / "src"),
)

from acquisition.contracts import (
    ProviderResult,
)
from acquisition.models import (
    SourcePostBundle,
)
from generation.source_grounded_caption import (
    SourceGroundedCaptionService,
)


class NaturalCopyeditProvider:
    provider_name = "natural_copyedit_fixture"
    provider_version = "1"

    def generate(
        self,
        *_args,
        **_kwargs,
    ):
        return ProviderResult(
            self.provider_name,
            self.provider_version,
            "PASS",
            data={
                "internal_analysis": {
                    "main_claims": [
                        (
                            "配信では初見さんが"
                            "入りやすい空気を"
                            "作ることが大切です。"
                        )
                    ],
                },
                "public_post_text": (
                    "配信を始める時は、"
                    "初見さんが入りやすい"
                    "空気を作ることが大切です。"
                ),
                "claim_support": [],
                "blocked_reasons": [],
            },
        )


class DriftedCopyeditProvider:
    provider_name = "drifted_copyedit_fixture"
    provider_version = "1"

    def generate(
        self,
        *_args,
        **_kwargs,
    ):
        return ProviderResult(
            self.provider_name,
            self.provider_version,
            "PASS",
            data={
                "internal_analysis": {
                    "main_claims": [
                        (
                            "配信時間と休みを"
                            "毎週決めるべきです。"
                        )
                    ],
                },
                "public_post_text": (
                    "配信を長く続けるには、"
                    "一週間単位で配信時間と"
                    "休みを先に決めた方がいいです。"
                ),
                "claim_support": [
                    {
                        "caption_claim": (
                            "一週間単位で"
                            "配信時間を決める。"
                        ),
                        "source_evidence": (
                            "存在しない根拠"
                        ),
                    }
                ],
                "blocked_reasons": [],
            },
        )


post = SourcePostBundle(
    source_post_id="sp_1",
    source_id="source_1",
    target_account_id="liver_manager",
    platform="tiktok",
    profile_url=(
        "https://www.tiktok.com/@allowed"
    ),
    canonical_post_url=(
        "https://www.tiktok.com/"
        "@allowed/video/1"
    ),
    external_post_id="1",
    original_post_text=(
        "配信では初見さんが"
        "入りやすい空気を"
        "作ることが大切です。"
    ),
    published_at="",
)


natural = SourceGroundedCaptionService(
    NaturalCopyeditProvider(),
    allow_deterministic_fallback=True,
).generate(
    post,
    account_id="liver_manager",
    source_mode="source_copyedit",
)

assert natural["status"] == "PASS", (
    natural
)

assert (
    natural["source_mode"]
    == "source_copyedit"
), natural

assert (
    natural["provider_name"]
    == "natural_copyedit_fixture"
), natural

assert (
    natural["primary_attempt_count"]
    == 1
), natural

assert (
    natural[
        "source_copyedit_contract"
    ]["status"]
    == "PASS"
), natural

assert (
    natural[
        "semantic_alignment"
    ]["status"]
    == "PASS"
), natural


drifted = SourceGroundedCaptionService(
    DriftedCopyeditProvider(),
    allow_deterministic_fallback=True,
).generate(
    post,
    account_id="liver_manager",
    source_mode="source_copyedit",
)

assert drifted["status"] == "PASS", (
    drifted
)

assert (
    drifted["source_mode"]
    == "source_copyedit"
), drifted

assert (
    drifted["provider_name"]
    == "deterministic_source_copyedit"
), drifted

assert (
    drifted["primary_attempt_count"]
    == 2
), drifted

assert (
    drifted[
        "source_copyedit_contract"
    ]["status"]
    == "PASS"
), drifted

assert (
    drifted[
        "semantic_alignment"
    ]["status"]
    == "PASS"
), drifted

assert (
    "初見さんが入りやすい空気"
    in drifted["public_post_text"]
), drifted

assert (
    "一週間単位"
    not in drifted["public_post_text"]
), drifted

print(
    "PASS "
    "test_source_grounded_caption_"
    "alignment_fallback.py"
)
