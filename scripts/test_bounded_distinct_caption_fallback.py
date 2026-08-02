#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import public_post_quality
from generation.semantic_alignment import (
    ALIGNMENT_THRESHOLDS,
)
from generation.source_grounded_caption import (
    DeterministicGroundedProvider,
)


assert (
    ALIGNMENT_THRESHOLDS[
        "recent_post_similarity"
    ]
    == 0.75
)

assert (
    DeterministicGroundedProvider
    .MAX_GENERATION_ATTEMPTS
    == 64
)

assert (
    DeterministicGroundedProvider
    .MAX_DISTINCT_CANDIDATES
    == 18
)


post = SimpleNamespace(
    original_post_text=(
        "体験入店の候補が二つある時は、"
        "比べる判断軸を先に決める。"
        "報酬、来客の多さ、"
        "店が忙しくなる時間、"
        "相談できる人がいるかを並べる。"
        "目先の売上だけでなく、"
        "無理のない出勤を"
        "毎週続けられるかまで見て選ぶ。"
    ),
    content_hash="a" * 64,
    media_type="image",
)

duplicate_text = (
    "店を比べる時は、表示された時給だけで"
    "判断しない方がいい。"
    "\n\n"
    "客入りや条件を分けて確認すると、"
    "働き始めた後の違いが見えやすい。"
    "\n\n"
    "最後は、自分が無理なく続けられる店か"
    "まで整理して決めたい。"
)

distinct_text = (
    "体験入店が二つ決まって迷う時は、"
    "最初に比較項目を揃えたい。"
    "\n\n"
    "時給、客入り、忙しい時間帯、"
    "スタッフへ相談しやすいかを"
    "同じ順番で確認する。"
    "\n\n"
    "一日の数字だけではなく、"
    "毎週無理なく出勤できる環境かまで"
    "見てから決める方が判断しやすい。"
)


def output(text: str) -> dict[str, object]:
    return {
        "public_post_text": text,
        "blocked_reasons": [],
        "grounding_summary": {
            "topic": "conditions",
        },
    }


original_generator = (
    public_post_quality
    .generate_grounded_reader_facing_post
)

try:
    calls: list[dict[str, object]] = []

    def first_duplicate_then_distinct(
        *_args,
        **kwargs,
    ):
        calls.append(dict(kwargs))

        return output(
            duplicate_text
            if len(calls) == 1
            else distinct_text
        )

    public_post_quality.generate_grounded_reader_facing_post = (
        first_duplicate_then_distinct
    )

    provider = DeterministicGroundedProvider()

    result = provider.generate(
        post,
        account_id="night_scout",
        recent_posts=[
            duplicate_text
        ],
    )

    assert result.status == "PASS"
    assert result.ok
    assert result.data is not None

    assert (
        result.data[
            "public_post_text"
        ]
        == distinct_text
    )

    assert len(calls) == 2

    assert (
        result.metadata[
            "generation_attempt_count"
        ]
        == 2
    )

    assert (
        result.metadata[
            "distinct_candidate_count"
        ]
        == 2
    )

    assert (
        result.data[
            "blocked_reasons"
        ]
        == []
    )

    assert (
        result.data[
            "internal_analysis"
        ][
            "fallback_candidate_count"
        ]
        == 2
    )

    exhausted_calls: list[
        dict[str, object]
    ] = []

    def always_duplicate(
        *_args,
        **kwargs,
    ):
        exhausted_calls.append(
            dict(kwargs)
        )

        return output(
            duplicate_text
        )

    public_post_quality.generate_grounded_reader_facing_post = (
        always_duplicate
    )

    exhausted = provider.generate(
        post,
        account_id="night_scout",
        recent_posts=[
            duplicate_text
        ],
    )

    assert exhausted.status == "BLOCKED"
    assert not exhausted.ok

    assert (
        exhausted.reason
        == (
            "deterministic_distinct_"
            "candidate_exhausted"
        )
    )

    assert (
        len(exhausted_calls)
        == provider.MAX_GENERATION_ATTEMPTS
    )

    assert (
        exhausted.metadata[
            "distinct_candidate_count"
        ]
        == 1
    )

finally:
    public_post_quality.generate_grounded_reader_facing_post = (
        original_generator
    )


print(
    "PASS "
    "test_bounded_distinct_caption_fallback.py"
)
