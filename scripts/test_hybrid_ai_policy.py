#!/usr/bin/env python3
from __future__ import annotations

from hybrid_ai_policy import chunk_candidates, decide_route, estimate_requests, requires_hybrid_ai_gate


def main() -> None:
    source_copy = {
        "account_id": "liver_manager",
        "platform": "threads",
        "caption_mode": "source_copyedit",
        "generation_mode": "direct_reference_media",
    }
    assert requires_hybrid_ai_gate(source_copy)
    assert decide_route(source_copy).route == "external_direct_source_copyedit"
    assert decide_route(source_copy).estimated_requests == 3
    external_transform = {
        **source_copy,
        "caption_mode": "transform",
        "transformation_type": "transform",
        "media_origin": "direct_reference",
    }
    assert decide_route(external_transform).route == "external_direct_transform"
    assert decide_route(external_transform).estimated_requests == 3
    owned = {
        "account_id": "night_scout",
        "platform": "threads",
        "source_id": "system_owned_example",
        "media_origin": "direct_reference",
    }
    assert decide_route(owned).route == "owned_media_transform"
    beauty_prepared = {
        "account_id": "beauty_account",
        "platform": "threads",
        "generation_mode": "beauty_new_text_generation",
        "generated_by": "prepare_beauty_review_candidates.py",
        "semantic_voice_status": "PENDING_HYBRID_AI_REVIEW",
    }
    assert decide_route(beauty_prepared).route == "semantic_review"
    assert decide_route(beauty_prepared).generate is False
    assert decide_route(beauty_prepared).estimated_requests == 2
    candidates = [source_copy, owned, {"account_id": "night_scout", "platform": "threads", "generation_mode": "reference_text"}]
    assert estimate_requests(candidates) == 9
    batches = chunk_candidates(candidates, max_requests_per_batch=6)
    assert len(batches) == 2
    assert batches[0]["estimated_requests"] == 6
    assert batches[1]["estimated_requests"] == 3
    print("PASS 13 tests")


if __name__ == "__main__":
    main()
