#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).with_name("audit_media_activation_quality_evidence.py")
SPEC = importlib.util.spec_from_file_location("quality_evidence_audit", MODULE_PATH)
assert SPEC is not None
assert SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def complete_candidate(account: str, route: str) -> dict[str, object]:
    row: dict[str, object] = {
        "account_id": account,
        "content_route": route,
        "public_post_text": "検証済みの公開文です。",
        "validator_status": "PASS",
        "internal_leak_status": "PASS",
        "account_fit_status": "PASS",
        "alignment_status": "PASS",
        "final_alignment_score": "1",
        "main_claim_coverage": "1",
        "unsupported_claim_count": "0",
        "source_copy_similarity": "0.2",
        "recent_post_similarity": "0.1",
        "claim_support_json": "[]",
        "batch_id": "batch_1",
        "batch_diversity_status": "PASS",
        "primary_topic": "配信",
        "topic_confidence": "0.9",
        "topic_coherence_status": "PASS",
        "structure_variant": "guide",
        "hook_topic_match": "true",
        "closing_topic_match": "true",
        "quality_gate_version": "generation_quality_v3",
        "feature_schema_version": "post_features_v1",
        "media_primary_topic": "配信",
        "visual_topic": "配信",
        "visual_topic_match": "true",
        "visual_cta_match": "true",
        "visual_plan_version": "visual_plan_v1",
        "visual_text_hash": "visual_hash",
    }
    if route == "direct_reference_media":
        row.update({"source_post_id": f"sp_{account}", "media_asset_id": f"ma_{account}"})
    else:
        row.update(
            {
                "source_video_id": f"sv_{account}",
                "clip_candidate_id": f"clip_{account}",
                "media_asset_id": f"ma_clip_{account}",
            }
        )
    return row


def plan_with(candidates: list[dict[str, object]]) -> dict[str, object]:
    diagnostics = []
    present = {(str(row["account_id"]), str(row["content_route"])) for row in candidates}
    for account in module.ACCOUNTS:
        for route in module.ROUTES:
            if (account, route) in present:
                row = next(
                    item
                    for item in candidates
                    if item["account_id"] == account and item["content_route"] == route
                )
                blockers = [] if row.get("batch_id") else ["batch_id_missing"]
                diagnostics.append(
                    {
                        "account_id": account,
                        "content_route": route,
                        "blockers": blockers,
                    }
                )
    return {
        "candidates": candidates,
        "candidate_diagnostics": diagnostics,
        "selection_diagnostics": {
            "night_scout": {
                "direct_blocked_reasons": ["direct_missing"],
                "clip_blocked_reasons": ["clip_missing"],
            },
            "liver_manager": {
                "direct_blocked_reasons": [],
                "clip_blocked_reasons": [],
            },
        },
    }


def by_slot(report: dict[str, object], account: str, route: str) -> dict[str, object]:
    return next(
        row
        for row in report["slots"]  # type: ignore[index]
        if row["account_id"] == account and row["content_route"] == route
    )


def test_missing_source_is_explicit() -> None:
    report = module.build_quality_evidence_audit(
        plan_with([]),
        semantic_alignment_runs=[],
        content_understanding_runs=[],
    )
    slot = by_slot(report, "night_scout", "approved_source_clip")
    assert slot["status"] == "SOURCE_MISSING"
    assert slot["next_action"] == "SOURCE_REPAIR_REQUIRED"
    assert slot["selection_blocked_reasons"] == ["clip_missing"]


def test_direct_alignment_without_public_text_is_not_joinable() -> None:
    candidate = complete_candidate("liver_manager", "direct_reference_media")
    candidate.pop("public_post_text")
    candidate.pop("batch_id")
    report = module.build_quality_evidence_audit(
        plan_with([candidate]),
        semantic_alignment_runs=[
            {
                "alignment_id": "sa_direct",
                "account_id": "liver_manager",
                "source_post_id": "sp_liver_manager",
                "status": "PASS",
                "final_alignment_score": "1",
                "main_claim_coverage": "1",
                "unsupported_claim_count": "0",
                "source_copy_similarity": "0.2",
                "recent_post_similarity": "0.1",
                "claim_support_json": "[]",
                "public_post_hash": "unusable_without_text",
            }
        ],
        content_understanding_runs=[],
    )
    slot = by_slot(report, "liver_manager", "direct_reference_media")
    assert slot["semantic_evidence"]["match_type"] == "EXACT_SOURCE_POST"
    assert slot["semantic_evidence"]["joinable"] is False
    assert slot["semantic_evidence"]["public_post_hash_status"] == "NO_PUBLIC_TEXT"
    assert slot["next_action"] == "CAPTION_AND_FULL_QUALITY_GENERATION_REQUIRED"


def test_exact_clip_alignment_hash_match_is_joinable() -> None:
    candidate = complete_candidate("liver_manager", "approved_source_clip")
    for field in module.ALIGNMENT_FIELDS:
        candidate.pop(field, None)
    candidate.pop("batch_id")
    text = str(candidate["public_post_text"])
    report = module.build_quality_evidence_audit(
        plan_with([candidate]),
        semantic_alignment_runs=[
            {
                "alignment_id": "sa_clip",
                "account_id": "liver_manager",
                "source_video_id": "sv_liver_manager",
                "clip_candidate_id": "clip_liver_manager",
                "status": "PASS",
                "final_alignment_score": "1",
                "main_claim_coverage": "1",
                "unsupported_claim_count": "0",
                "source_copy_similarity": "0.2",
                "recent_post_similarity": "0.1",
                "claim_support_json": "[]",
                "public_post_hash": sha(text),
            }
        ],
        content_understanding_runs=[],
    )
    slot = by_slot(report, "liver_manager", "approved_source_clip")
    assert slot["status"] == "EXISTING_ALIGNMENT_JOINABLE"
    assert slot["semantic_evidence"]["match_type"] == "EXACT_CLIP"
    assert slot["semantic_evidence"]["public_post_hash_status"] == "MATCH"
    assert slot["semantic_evidence"]["joinable"] is True
    assert slot["next_action"] == "JOIN_ALIGNMENT_THEN_GENERATE_DESIGN_EVIDENCE"


def test_hash_mismatch_blocks_reuse() -> None:
    candidate = complete_candidate("liver_manager", "approved_source_clip")
    candidate.pop("batch_id")
    report = module.build_quality_evidence_audit(
        plan_with([candidate]),
        semantic_alignment_runs=[
            {
                "alignment_id": "sa_clip",
                "account_id": "liver_manager",
                "clip_candidate_id": "clip_liver_manager",
                "status": "PASS",
                "final_alignment_score": "1",
                "main_claim_coverage": "1",
                "unsupported_claim_count": "0",
                "source_copy_similarity": "0.2",
                "recent_post_similarity": "0.1",
                "claim_support_json": "[]",
                "public_post_hash": sha("別の投稿文"),
            }
        ],
        content_understanding_runs=[],
    )
    slot = by_slot(report, "liver_manager", "approved_source_clip")
    assert slot["semantic_evidence"]["joinable"] is False
    assert slot["semantic_evidence"]["public_post_hash_status"] == "MISMATCH"


def test_parent_video_alignment_is_not_exact_clip_evidence() -> None:
    candidate = complete_candidate("liver_manager", "approved_source_clip")
    candidate.pop("batch_id")
    text = str(candidate["public_post_text"])
    report = module.build_quality_evidence_audit(
        plan_with([candidate]),
        semantic_alignment_runs=[
            {
                "alignment_id": "sa_parent",
                "account_id": "liver_manager",
                "source_video_id": "sv_liver_manager",
                "clip_candidate_id": "",
                "status": "PASS",
                "final_alignment_score": "1",
                "main_claim_coverage": "1",
                "unsupported_claim_count": "0",
                "source_copy_similarity": "0.2",
                "recent_post_similarity": "0.1",
                "claim_support_json": "[]",
                "public_post_hash": sha(text),
            }
        ],
        content_understanding_runs=[],
    )
    slot = by_slot(report, "liver_manager", "approved_source_clip")
    assert slot["semantic_evidence"]["match_type"] == "PARENT_VIDEO_ONLY"
    assert slot["semantic_evidence"]["joinable"] is False
    assert slot["semantic_evidence"]["blocked_reason"] == "semantic_identity_not_exact"


def test_understanding_match_is_reported_but_not_treated_as_caption_evidence() -> None:
    candidate = complete_candidate("liver_manager", "approved_source_clip")
    candidate.pop("batch_id")
    report = module.build_quality_evidence_audit(
        plan_with([candidate]),
        semantic_alignment_runs=[],
        content_understanding_runs=[
            {
                "understanding_id": "cu_parent",
                "account_id": "liver_manager",
                "source_video_id": "sv_liver_manager",
                "status": "PASS",
                "provider_name": "provider",
                "provider_version": "v1",
            }
        ],
    )
    slot = by_slot(report, "liver_manager", "approved_source_clip")
    assert slot["understanding_evidence"]["match_type"] == "PARENT_VIDEO"
    assert slot["understanding_evidence"]["status"] == "PASS"
    assert slot["semantic_evidence"]["joinable"] is False


def test_complete_candidate_remains_complete() -> None:
    candidates = [
        complete_candidate(account, route)
        for account in module.ACCOUNTS
        for route in module.ROUTES
    ]
    report = module.build_quality_evidence_audit(
        plan_with(candidates),
        semantic_alignment_runs=[],
        content_understanding_runs=[],
    )
    assert report["audit_status"] == "PASS"
    assert report["quality_complete_count"] == 4
    assert all(row["next_action"] == "QUALITY_EVIDENCE_COMPLETE" for row in report["slots"])


def test_unsafe_environment_is_blocked() -> None:
    assert module.safety_blockers({"PUBLISH_ENABLED": "true"}) == ["PUBLISH_ENABLED=true"]


def main() -> int:
    tests = [
        test_missing_source_is_explicit,
        test_direct_alignment_without_public_text_is_not_joinable,
        test_exact_clip_alignment_hash_match_is_joinable,
        test_hash_mismatch_blocks_reuse,
        test_parent_video_alignment_is_not_exact_clip_evidence,
        test_understanding_match_is_reported_but_not_treated_as_caption_evidence,
        test_complete_candidate_remains_complete,
        test_unsafe_environment_is_blocked,
    ]
    for test in tests:
        test()
    print(f"PASS {len(tests)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
