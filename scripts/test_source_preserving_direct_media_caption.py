#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

from acquisition.contracts import ProviderResult
from acquisition.models import SourcePostBundle
from generation.semantic_alignment import (
    ALIGNMENT_THRESHOLDS,
)
from generation.source_copyedit import (
    SOURCE_PRESERVATION_MIN,
    clean_source_post_text,
    evaluate_source_copyedit_contract,
    validate_source_preserving_public_post,
)
from generation.source_grounded_caption import (
    SourceGroundedCaptionService,
)
from media_post_validator import (
    validate_media_post,
)

assert (
    ALIGNMENT_THRESHOLDS[
        "source_copy_similarity"
    ]
    == 0.65
)

assert (
    ALIGNMENT_THRESHOLDS[
        "recent_post_similarity"
    ]
    == 0.75
)

assert (
    ALIGNMENT_THRESHOLDS[
        "source_preservation_similarity"
    ]
    == SOURCE_PRESERVATION_MIN
)


class UnavailableProvider:
    provider_name = "unavailable_fixture"
    provider_version = "1"

    def generate(
        self,
        *_args,
        **_kwargs,
    ):
        return ProviderResult(
            self.provider_name,
            self.provider_version,
            "UNAVAILABLE",
            reason="fixture_unavailable",
        )


night_source = (
    "時給はフジコの方が出ると思うし"
    "客入りもいいし一時店だしフジコかな "
    "お店のお客さんに刺さるように"
    "立ち回りしてみて"
)

night_post = SourcePostBundle(
    source_post_id="sp_night",
    source_id="src_night",
    target_account_id="night_scout",
    platform="threads",
    profile_url=(
        "https://www.threads.com/@allowed"
    ),
    canonical_post_url=(
        "https://www.threads.com/"
        "@allowed/post/1"
    ),
    external_post_id="1",
    original_post_text=night_source,
    published_at="",
)

night_result = (
    SourceGroundedCaptionService(
        UnavailableProvider(),
        allow_deterministic_fallback=True,
    ).generate(
        night_post,
        account_id="night_scout",
        source_mode="source_copyedit",
    )
)

assert night_result["status"] == "PASS", (
    night_result
)

assert (
    night_result["source_mode"]
    == "source_copyedit"
)

assert (
    night_result["provider_name"]
    == "deterministic_source_copyedit"
)

night_text = night_result[
    "public_post_text"
]

assert "フジコ" in night_text
assert "客入り" in night_text
assert "と思う" in night_text
assert "かな" in night_text

for phrase in (
    "確認することは一つ。",
    "この順番で考える理由はシンプル。",
    "見るポイントは次の通り。",
    "次に試すこと：",
):
    assert phrase not in night_text

night_validation = (
    validate_source_preserving_public_post(
        night_text,
        "night_scout",
    )
)

assert (
    night_validation["status"]
    == "PASS"
), night_validation

night_alignment = night_result[
    "semantic_alignment"
]

assert (
    night_alignment[
        "alignment_mode"
    ]
    == "source_copyedit"
)

assert (
    float(
        night_alignment[
            "source_copy_similarity"
        ]
    )
    >= SOURCE_PRESERVATION_MIN
)

generic_night = (
    "求人の時給が高く見えても、"
    "実際の手取りは別に確認したい。"
    "\n\n"
    "体験入店と本入後で条件が"
    "変わらないかを確認する。"
    "\n\n"
    "店を比べる時は控除後の"
    "手取りで判断したい。"
)

generic_night_contract = (
    evaluate_source_copyedit_contract(
        source_text=night_source,
        public_post_text=generic_night,
        account_id="night_scout",
        recent_posts=[],
    )
)

assert (
    generic_night_contract["status"]
    == "BLOCKED"
)

assert (
    "source_preservation_similarity_below_threshold"
    in generic_night_contract[
        "blocked_reasons"
    ]
    or "source_fact_removed"
    in generic_night_contract[
        "blocked_reasons"
    ]
)

repeated_tone = (
    "フジコが良さそうなんよな。"
    "客入りもいいんよな。"
    "時給も高いんよな。"
    "僕ならフジコかな。"
)

repeated_contract = (
    evaluate_source_copyedit_contract(
        source_text=night_source,
        public_post_text=repeated_tone,
        account_id="night_scout",
        recent_posts=[],
    )
)

assert (
    "account_conversational_ending_overuse"
    in repeated_contract[
        "blocked_reasons"
    ]
)


liver_source = (
    "推しが料理をしてる時は、"
    "黙って見てるんじゃなくて。"
    "主の料理を手伝うのが"
    "リスナーとしての責務だよね！"
    "肉が焦げたらリスナーの責任。"
    "これがリスナーの鑑です。"
    "と思いつつ、今度焦げた肉を"
    "食べさせた時の反応を"
    "切り抜きたい欲求もあるのが"
    "リスナーというものです。 "
    "@sample #tiktoklive #切り抜き"
)

liver_cleaned = (
    clean_source_post_text(
        liver_source,
        "liver_manager",
    )
)

assert "@sample" not in liver_cleaned
assert "#tiktoklive" not in liver_cleaned
assert "料理" in liver_cleaned
assert "リスナー" in liver_cleaned
assert "焦げた肉" in liver_cleaned

liver_validation = (
    validate_source_preserving_public_post(
        liver_cleaned,
        "liver_manager",
    )
)

assert (
    liver_validation["status"]
    == "PASS"
), liver_validation

generic_liver = (
    "ライバーが配信を続けるには、"
    "毎回の気合いより休んでも"
    "戻れる仕組みが必要。"
    "\n\n"
    "一週間単位で配信時間と"
    "休みを決める。"
)

generic_liver_contract = (
    evaluate_source_copyedit_contract(
        source_text=liver_source,
        public_post_text=generic_liver,
        account_id="liver_manager",
        recent_posts=[],
    )
)

assert (
    generic_liver_contract["status"]
    == "BLOCKED"
)

assert (
    "source_preservation_similarity_below_threshold"
    in generic_liver_contract[
        "blocked_reasons"
    ]
    or "source_fact_removed"
    in generic_liver_contract[
        "blocked_reasons"
    ]
)


media_plan = {
    "rights_status": (
        "approved_creator_clip"
    ),
    "permission_status": "approved",
    "media_url": (
        "https://res.cloudinary.com/"
        "example/image/upload/test.jpg"
    ),
    "media_asset_id": "ma_test",
    "platform": "threads",
    "account_id": "night_scout",
    "media_type": "image",
    "media_origin": (
        "direct_reference"
    ),
    "caption_mode": (
        "source_copyedit"
    ),
    "public_post_text": night_text,
    "alignment_status": "PASS",
    "final_alignment_score": (
        night_alignment[
            "final_alignment_score"
        ]
    ),
    "main_claim_coverage": (
        night_alignment[
            "main_claim_coverage"
        ]
    ),
    "unsupported_claim_count": (
        night_alignment[
            "unsupported_claim_count"
        ]
    ),
    "source_copy_similarity": (
        night_alignment[
            "source_copy_similarity"
        ]
    ),
    "recent_post_similarity": (
        night_alignment[
            "recent_post_similarity"
        ]
    ),
}

media_result = validate_media_post(
    media_plan
)

assert (
    media_result["status"]
    == "PASS"
), media_result

old_invalid_ready = {
    **media_plan,
    "source_copy_similarity": 0.1491,
}

old_invalid_result = (
    validate_media_post(
        old_invalid_ready
    )
)

assert (
    old_invalid_result["status"]
    == "BLOCKED"
)

assert (
    "source_preservation_similarity_below_threshold"
    in old_invalid_result[
        "blocked_reasons"
    ]
)

transform_copy = {
    **media_plan,
    "media_origin": (
        "approved_source_clip"
    ),
    "caption_mode": (
        "transform"
    ),
    "source_copy_similarity": 0.90,
}

transform_result = (
    validate_media_post(
        transform_copy
    )
)

assert (
    "source_copy_similarity_above_threshold"
    in transform_result[
        "blocked_reasons"
    ]
)


process_source = (
    ROOT
    .joinpath(
        "scripts/process_threads_queue.py"
    )
    .read_text(
        encoding="utf-8",
    )
)

process_one_source = (
    process_source.split(
        "def process_one",
        1,
    )[1]
)

assert (
    process_one_source.index(
        "direct_media_validation"
    )
    < process_one_source.index(
        "if dry_run:\n        return {"
    )
)

pipeline_source = (
    ROOT
    .joinpath(
        "scripts/"
        "run_direct_reference_media_pipeline.py"
    )
    .read_text(
        encoding="utf-8",
    )
)

assert (
    "source_post_text_unusable"
    in pipeline_source
)

assert (
    "validate_source_preserving_public_post"
    in pipeline_source
)

assert (
    'source_mode="source_copyedit"'
    in pipeline_source
)

print(
    "PASS "
    "test_source_preserving_"
    "direct_media_caption.py"
)
