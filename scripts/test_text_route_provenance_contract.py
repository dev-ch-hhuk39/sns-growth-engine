#!/usr/bin/env python3
"""Preserve scheduled text route independently from generation method."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT),
    str(ROOT / "src"),
    str(ROOT / "scripts"),
]

from sheets_client import TAB_DEFINITIONS

REQUIRED = {
    "content_route",
    "source_content_route",
    "source_generation_mode",
    "source_result_id",
}

for logical in (
    "drafts",
    "queue",
    "posted_results",
):
    missing = REQUIRED - set(
        TAB_DEFINITIONS[logical]
    )

    assert not missing, {
        "logical": logical,
        "missing": sorted(missing),
    }


import generate_threads_ideas_from_references as generation

original_generate = generation.generate_production_post
original_validator = generation.final_public_post_validator
original_quality = generation.evaluate_generation_quality
original_feature_fields = generation._feature_fields
original_similarity = generation.original_text_similarity_guard

try:
    generation.generate_production_post = (
        lambda *_args, **_kwargs: {
            "public_post_text": (
                "店選びでは時給だけでなく、"
                "客層や相談しやすさも確認することが大切です。"
                "\n\n"
                "まずは無理なく続けられる条件を"
                "一つずつ整理してみてください。"
            ),
            "grounding_summary": {
                "structure_variant": "0",
                "quality_topic": "work_conditions",
            },
        }
    )

    generation.final_public_post_validator = (
        lambda *_args, **_kwargs: {
            "status": "PASS",
            "internal_leak_check": {
                "status": "PASS",
            },
            "account_fit_check": {
                "status": "PASS",
            },
            "public_post_quality_score": 95,
            "reader_value_score": 90,
            "naturalness_score": 90,
            "cta_pressure_score": 0,
        }
    )

    generation.evaluate_generation_quality = (
        lambda *_args, **_kwargs: {
            "status": "PASS",
            "primary_topic": "work_conditions",
            "structure_variant": "0",
        }
    )

    generation._feature_fields = (
        lambda *_args, **_kwargs: {
            "feature_schema_version": "post_features_v1",
            "primary_topic": "work_conditions",
        }
    )

    generation.original_text_similarity_guard = (
        lambda *_args, **_kwargs: {
            "status": "PASS",
            "similarity": 0.0,
        }
    )

    rows = generation.build_fallback_generation_rows(
        account_id="night_scout",
        top_n=1,
        slot_id="ns_2500_pdca",
        post_type="original_text",
        content_route="pdca_text",
        theme="future_options",
        schedule_date_jst="2026-08-02",
        fallback_reason="pdca_metrics_unavailable",
    )

finally:
    generation.generate_production_post = (
        original_generate
    )
    generation.final_public_post_validator = (
        original_validator
    )
    generation.evaluate_generation_quality = (
        original_quality
    )
    generation._feature_fields = (
        original_feature_fields
    )
    generation.original_text_similarity_guard = (
        original_similarity
    )

assert len(rows["queue"]) == 1, rows

fallback_queue = rows["queue"][0]
fallback_draft = rows["drafts"][0]

assert (
    fallback_queue["content_route"]
    == "pdca_text"
), fallback_queue

assert (
    fallback_queue["generation_mode"]
    == "original_text"
), fallback_queue

assert (
    fallback_queue["content_type"]
    == "original_text"
), fallback_queue

assert (
    fallback_draft["content_route"]
    == "pdca_text"
), fallback_draft


import generate_next_queue_from_metrics as next_queue

posted = [
    {
        "result_id": "result_reference_winner",
        "account_id": "liver_manager",
        "platform": "threads",
        "metrics_status": "MEASURED",
        "views": 1000,
        "likes": 100,
        "comments": 20,
        "content_type": "reference_text",
        "content_route": "reference_text",
        "generation_mode": (
            "reference_score_to_threads"
        ),
        "slot_id": "lm_1300_reference",
        "theme": "first_viewer_experience",
    }
]

ranked = next_queue.rank_results_by_engagement(
    posted,
    "liver_manager",
)

assert ranked[0]["content_route"] == "reference_text"
assert (
    ranked[0]["generation_mode"]
    == "reference_score_to_threads"
)

drafts, queues, suggestion = (
    next_queue.build_next_queue_candidates(
        ranked,
        "liver_manager",
        1,
        "20260802000000",
    )
)

assert len(drafts) == 1
assert len(queues) == 1

pdca_queue = queues[0]
pdca_draft = drafts[0]

for row in (
    pdca_queue,
    pdca_draft,
):
    assert row["content_route"] == "pdca_text"
    assert (
        row["source_content_route"]
        == "reference_text"
    )
    assert (
        row["source_generation_mode"]
        == "reference_score_to_threads"
    )
    assert (
        row["source_result_id"]
        == "result_reference_winner"
    )

assert (
    pdca_queue["generation_mode"]
    == "metrics_driven_candidate"
)

assert pdca_queue["content_type"] == "pdca_text"
assert pdca_queue["status"] == "DRAFT"
assert pdca_queue["auto_publish"] == "false"
assert suggestion["status"] == "WAITING_REVIEW"


import process_threads_queue as publisher

captured: list[tuple[str, dict[str, Any]]] = []
original_append = publisher.append_row

try:
    publisher.append_row = (
        lambda _client, logical, row: (
            captured.append(
                (
                    logical,
                    dict(row),
                )
            )
            or True
        )
    )

    publisher.save_posted_result(
        object(),
        queue_row={
            "queue_id": "queue_pdca",
            "draft_id": "draft_pdca",
            "account_id": "liver_manager",
            "generation_mode": (
                "metrics_driven_candidate"
            ),
            "content_type": "pdca_text",
            "content_route": "pdca_text",
            "source_content_route": (
                "reference_text"
            ),
            "source_generation_mode": (
                "reference_score_to_threads"
            ),
            "source_result_id": (
                "result_reference_winner"
            ),
        },
        social=None,
        text=(
            "配信の改善では、前回の数字を見ながら"
            "次の一つを決めてみてください。"
        ),
        external_post_id="external_1",
        post_url=(
            "https://www.threads.com/"
            "@example/post/1"
        ),
        validator_status="PASS",
    )

finally:
    publisher.append_row = original_append

posted_rows = [
    row
    for logical, row in captured
    if logical == "posted_results"
]

assert len(posted_rows) == 1, captured

posted_row = posted_rows[0]

assert posted_row["content_route"] == "pdca_text"
assert (
    posted_row["generation_mode"]
    == "metrics_driven_candidate"
)
assert (
    posted_row["source_content_route"]
    == "reference_text"
)
assert (
    posted_row["source_generation_mode"]
    == "reference_score_to_threads"
)
assert (
    posted_row["source_result_id"]
    == "result_reference_winner"
)


import import_posted_results as importer

normalized = importer.normalize_result(
    {
        "result_id": "imported_1",
        "content_type": "pdca_text",
        "generation_mode": (
            "metrics_driven_candidate"
        ),
        "content_route": "pdca_text",
        "source_content_route": (
            "original_text"
        ),
        "source_generation_mode": (
            "original_text"
        ),
        "source_result_id": "source_result_1",
    },
    "night_scout",
)

assert normalized["content_route"] == "pdca_text"
assert (
    normalized["source_content_route"]
    == "original_text"
)
assert (
    normalized["source_generation_mode"]
    == "original_text"
)
assert (
    normalized["source_result_id"]
    == "source_result_1"
)

generation_source = (
    ROOT
    / "scripts"
    / "generate_threads_ideas_from_references.py"
).read_text(
    encoding="utf-8",
)

assert generation_source.count(
    "content_route=post_type"
) >= 4

print(
    "PASS "
    "test_text_route_provenance_contract.py"
)
