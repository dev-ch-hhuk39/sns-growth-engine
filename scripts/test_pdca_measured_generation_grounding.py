#!/usr/bin/env python3
from pathlib import Path

from generate_threads_ideas_from_references import (
    apply_measured_pdca_lineage,
    build_measured_pdca_inputs,
)

posted = [
    {
        "result_id": "r_high",
        "account_id": "night_scout",
        "platform": "threads",
        "status": "POSTED",
        "posted_text": (
            "体験入店では時給だけでなく、"
            "控除と客層まで確認する。"
        ),
        "content_route": "reference_text",
        "generation_mode": (
            "reference_score_to_threads"
        ),
        "post_url": (
            "https://www.threads.net/"
            "@example/post/high"
        ),
    },
    {
        "result_id": "r_low",
        "account_id": "night_scout",
        "platform": "threads",
        "status": "POSTED",
        "posted_text": (
            "夜職の出勤日は睡眠時間も"
            "先に決めておく。"
        ),
        "content_route": "original_text",
        "generation_mode": "original_text",
    },
]

measured = [
    {
        "snapshot_id": "s_high_24",
        "result_id": "r_high",
        "account_id": "night_scout",
        "platform": "threads",
        "metrics_status": "MEASURED",
        "collection_window_hours": 24,
        "collected_at": (
            "2026-08-01T00:00:00+00:00"
        ),
        "views": 100,
        "likes": 10,
        "comments": 2,
        "reposts": 1,
        "quotes": 0,
    },
    {
        "snapshot_id": "s_high_72",
        "result_id": "r_high",
        "account_id": "night_scout",
        "platform": "threads",
        "metrics_status": "MEASURED",
        "collection_window_hours": 72,
        "collected_at": (
            "2026-08-03T00:00:00+00:00"
        ),
        "views": 200,
        "likes": 30,
        "comments": 5,
        "reposts": 2,
        "quotes": 1,
    },
    {
        "snapshot_id": "s_low",
        "result_id": "r_low",
        "account_id": "night_scout",
        "platform": "threads",
        "metrics_status": "MEASURED",
        "collection_window_hours": 24,
        "collected_at": (
            "2026-08-02T00:00:00+00:00"
        ),
        "views": 300,
        "likes": 3,
        "comments": 0,
        "reposts": 0,
        "quotes": 0,
    },
]

posts, scores, source_meta = (
    build_measured_pdca_inputs(
        measured_rows=measured,
        posted_results=posted,
        account_id="night_scout",
    )
)

assert len(posts) == 12
assert len(scores) == 12

# Latest collection window is selected per
# result, then results are ranked by ER.
assert posts[0]["source_id"] == "r_high"

assert (
    source_meta["r_high"][
        "engagement_rate"
    ]
    > source_meta["r_low"][
        "engagement_rate"
    ]
)

assert (
    "night_scoutだけのMEASURED"
    in scores[0]["reason"]
)

fake_rows = {
    "drafts": [
        {
            "draft_id": "d1",
            "generation_mode": "pdca_text",
            "content_route": "pdca_text",
        },
        {
            "draft_id": "d2",
        },
    ],
    "social_derivatives": [
        {
            "draft_id": "d1",
        },
        {
            "draft_id": "d2",
        },
    ],
    "queue": [
        {
            "queue_id": "q1",
            "draft_id": "d1",
            "account_id": "night_scout",
            "source_id": "r_high",
            "public_post_text": (
                "体入で時給だけを見て決めると、"
                "給料日に思ったより残らないって"
                "なることが結構ある。\n\n"
                "僕が入店前に見るのは、控除の種類、"
                "早上がりの扱い、バックが付く条件。"
                "この3つなんだよね。\n\n"
                "表示時給より、同じ出勤ペースで実際に"
                "いくら残るかを見る。ここまで聞いてから"
                "選ぶ方が、自分に合う店を見つけやすいよ。"
            ),
        },
        {
            "queue_id": "q2",
            "draft_id": "d2",
            "source_id": "r_low",
        },
    ],
}

grounded = apply_measured_pdca_lineage(
    fake_rows,
    account_id="night_scout",
    source_meta=source_meta,
    top_n=1,
)

assert len(grounded["queue"]) == 1
assert len(grounded["drafts"]) == 1
assert len(
    grounded["social_derivatives"]
) == 1

queue = grounded["queue"][0]

assert (
    queue["generation_mode"]
    == "metrics_driven_pdca_text"
)

assert (
    queue["content_route"]
    == "pdca_text"
)

assert (
    queue["source_result_id"]
    == "r_high"
)

assert (
    queue["source_content_route"]
    == "reference_text"
)

assert (
    queue["transformation_type"]
    == "metrics_learned_original"
)

assert (
    queue["source_credit"]
    == "internal_learning_only"
)

assert queue["pdca_learning_scope_id"] == "account:night_scout"
assert queue["metrics_disclosure_status"] == "PASS"
assert "前回" not in queue["public_post_text"]

source = (
    Path(__file__)
    .resolve()
    .parents[1]
    / "scripts/"
    "generate_threads_ideas_from_references.py"
).read_text(
    encoding="utf-8"
)

assert (
    "strict_measured_pdca"
    in source
)

assert (
    "build_measured_pdca_generation_rows"
    in source
)

assert (
    "and not strict_measured_pdca"
    in source
)

print(
    "PASS "
    "test_pdca_measured_generation_grounding.py"
)
