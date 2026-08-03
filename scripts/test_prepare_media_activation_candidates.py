#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("prepare_media_activation_candidates.py")
SPEC = importlib.util.spec_from_file_location("media_activation", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def candidate(account: str, route: str) -> dict[str, object]:
    suffix = f"{account}_{route}"
    row: dict[str, object] = {
        "account_id": account,
        "content_route": route,
        "public_post_text": "公開用の検証済み本文です。",
        "source_id": f"src_{suffix}",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "permission_evidence": f"evidence_{suffix}",
        "media_asset_id": f"ma_{suffix}",
        "media_url": f"https://example.invalid/{suffix}.mp4",
        "publisher_media_type": "VIDEO",
        "validator_status": "PASS",
        "internal_leak_status": "PASS",
        "account_fit_status": "PASS",
        "alignment_status": "PASS",
        "final_alignment_score": "1",
        "main_claim_coverage": "1",
        "unsupported_claim_count": "0",
        "source_copy_similarity": "0.2",
        "recent_post_similarity": "0.1",
        "batch_id": "batch_test",
        "batch_diversity_status": "PASS",
        "primary_topic": "test",
        "topic_confidence": "0.9",
        "topic_coherence_status": "PASS",
        "structure_variant": "test_structure",
        "hook_topic_match": "true",
        "closing_topic_match": "true",
        "quality_gate_version": "generation_quality_v3",
        "feature_schema_version": "post_features_v1",
        "media_primary_topic": "test",
        "visual_topic": "test",
        "visual_topic_match": "true",
        "visual_cta_match": "true",
        "visual_plan_version": "visual_plan_v1",
        "visual_text_hash": f"hash_{suffix}",
        "claim_support_json": "[]",
    }
    if route == "direct_reference_media":
        row["source_post_id"] = f"sp_{suffix}"
    else:
        row.update(
            {
                "source_video_id": f"sv_{suffix}",
                "clip_candidate_id": f"clip_{suffix}",
                "start_seconds": "1",
                "end_seconds": "11",
            }
        )
    return row


def candidates() -> list[dict[str, object]]:
    return [
        candidate(account, route)
        for account in module.ACCOUNTS
        for route in module.ROUTES
    ]


def test_four_rows() -> None:
    plan = module.build_plan(candidates())
    assert plan["status"] == "PASS"
    assert plan["row_count"] == 4


def test_never_ready_or_publishable() -> None:
    plan = module.build_plan(candidates())
    for row in plan["rows"]:
        assert row["status"] == "WAITING_REVIEW"
        assert row["auto_publish"] == "false"
        assert row["posted_at"] == ""
        assert row["post_url"] == ""
        assert row["result_id"] == ""


def test_missing_evidence_blocks() -> None:
    rows = candidates()
    rows[0]["permission_evidence"] = ""
    plan = module.build_plan(rows)
    assert plan["status"] == "BLOCKED"
    assert any(
        "permission_evidence_missing" in item["blockers"]
        for item in plan["failures"]
    )


def test_duplicate_slot_blocks() -> None:
    rows = candidates()
    rows.append(dict(rows[0]))
    plan = module.build_plan(rows)
    assert plan["status"] == "BLOCKED"
    assert plan["duplicate_slots"]


if __name__ == "__main__":
    tests = (
        test_four_rows,
        test_never_ready_or_publishable,
        test_missing_evidence_blocks,
        test_duplicate_slot_blocks,
    )
    for test_case in tests:
        test_case()
    print(f"PASS {len(tests)} tests")
