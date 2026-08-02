#!/usr/bin/env python3
from generate_threads_ideas_from_references import (
    attach_pdca_activation_evidence,
)

rows = {
    "drafts": [],
    "social_derivatives": [],
    "queue": [
        {
            "queue_id": "q1",
            "content_type": "pdca_text",
            "content_route": "pdca_text",
            "source_result_id": "r2",
            "source_content_route": (
                "reference_text"
            ),
            "source_generation_mode": (
                "reference_score_to_threads"
            ),
        }
    ],
}

result = attach_pdca_activation_evidence(
    rows,
    account_id="night_scout",
    measured_rows=[
        {
            "snapshot_id": "s1",
            "result_id": "r1",
            "metrics_status": "MEASURED",
            "collected_at": (
                "2026-08-03T01:00:00+00:00"
            ),
        },
        {
            "snapshot_id": "s2",
            "result_id": "r2",
            "metrics_status": "MEASURED",
            "collected_at": (
                "2026-08-03T00:00:00+00:00"
            ),
        },
    ],
    posted_results=[
        {
            "result_id": "r1",
            "content_route": (
                "original_text"
            ),
            "generation_mode": (
                "original_text"
            ),
        },
        {
            "result_id": "r2",
            "content_route": (
                "reference_text"
            ),
            "generation_mode": (
                "reference_score_to_threads"
            ),
        },
    ],
    stamp="20260803000000",
)

queue = result["queue"][0]

assert queue["canary_id"].startswith(
    "canary_fresh_night_scout_"
    "pdca_text_"
)

assert (
    queue["content_route"]
    == "pdca_text"
)

assert (
    queue["generation_mode"]
    == "metrics_driven_pdca_text"
)

# Preserve the source selected by measured
# ranking instead of replacing it with the
# newest snapshot's result.
assert queue["source_result_id"] == "r2"

assert (
    queue["source_content_route"]
    == "reference_text"
)

assert (
    queue["source_generation_mode"]
    == "reference_score_to_threads"
)

assert "canary_id" not in rows["queue"][0]

print(
    "PASS "
    "test_pdca_activation_candidate_contract.py"
)
