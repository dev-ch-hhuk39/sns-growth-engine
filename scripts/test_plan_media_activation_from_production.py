#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent


def _load(name: str, filename: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


integration = _load("production_integration", "plan_media_activation_from_production.py")
planner = _load("activation_planner", "prepare_media_activation_candidates.py")


def _evidence(account: str, route: str, link: dict[str, str]) -> dict[str, Any]:
    suffix = f"{account}_{route}"
    return {
        "queue_id": f"evidence_{suffix}",
        "account_id": account,
        "content_route": route,
        "status": "WAITING_REVIEW",
        **link,
        "public_post_text": "公開用の検証済み本文です。",
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
    }


def _fixture() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    direct: dict[str, Any] = {}
    clips: dict[str, Any] = {}
    queue: list[dict[str, Any]] = []
    permissions: list[dict[str, Any]] = []
    for account in integration.ACCOUNTS:
        direct_source = f"src_direct_{account}"
        source_post_id = f"sp_{account}"
        direct[account] = (
            {
                "source_post_id": source_post_id,
                "source_id": direct_source,
                "canonical_post_url": f"https://threads.com/@x/post/{account}",
            },
            {
                "media_asset_id": f"ma_direct_{account}",
                "storage_url": f"https://media.invalid/{account}.mp4",
                "media_type": "video",
                "duration_seconds": "12",
                "aspect_ratio": "9:16",
            },
            {"source_id": direct_source},
        )
        queue.append(
            _evidence(
                account,
                "direct_reference_media",
                {"source_post_id": source_post_id},
            )
        )
        permissions.append(
            {
                "permission_id": f"perm_direct_{account}",
                "account_id": account,
                "source_id": direct_source,
                "rights_status": "approved_creator_clip",
                "permission_status": "approved",
                "evidence_reference": f"evidence_direct_{account}",
                "allow_original_repost": "true",
            }
        )

        clip_source = f"src_clip_{account}"
        clip_id = f"clip_{account}"
        clips[account] = (
            {
                "clip_candidate_id": clip_id,
                "source_video_id": f"sv_{account}",
                "start_seconds": "1",
                "end_seconds": "11",
            },
            {
                "source_video_id": f"sv_{account}",
                "source_id": clip_source,
                "canonical_video_url": f"https://youtube.com/watch?v={account[:11]:0<11}",
            },
            {
                "media_asset_id": f"ma_clip_{account}",
                "storage_url": f"https://media.invalid/{clip_id}.mp4",
                "duration_seconds": "10",
                "aspect_ratio": "9:16",
                "width": "1080",
                "height": "1920",
                "video_stream_count": "1",
                "audio_stream_count": "1",
                "media_probe_status": "PASS",
            },
        )
        queue.append(
            _evidence(
                account,
                "approved_source_clip",
                {"clip_candidate_id": clip_id},
            )
        )
        permissions.append(
            {
                "permission_id": f"perm_clip_{account}",
                "account_id": account,
                "source_id": clip_source,
                "rights_status": "approved_creator_clip",
                "permission_status": "approved",
                "evidence_reference": f"evidence_clip_{account}",
                "allow_clip_repost": "true",
            }
        )
    return direct, clips, queue, permissions


def _permission(row: dict[str, Any], *, account_id: str, operation: str) -> bool:
    field = "allow_original_repost" if operation == "direct" else "allow_clip_repost"
    return (
        row.get("account_id") == account_id
        and row.get("permission_status") == "approved"
        and row.get("rights_status") == "approved_creator_clip"
        and bool(row.get("evidence_reference"))
        and row.get(field) == "true"
    )


def _build() -> dict[str, Any]:
    direct, clips, queue, permissions = _fixture()
    return integration.build_production_plan(
        direct_selections=direct,
        clip_selections=clips,
        queue_rows=queue,
        permissions=permissions,
        permission_checker=_permission,
        planner=planner.build_plan,
        candidate_validator=planner.candidate_blockers,
    )


def test_complete_plan_is_review_only() -> None:
    report = _build()
    assert report["source_selection_status"] == "PASS"
    assert report["activation_plan_status"] == "PASS"
    assert report["candidate_count"] == 4
    rows = report["activation_plan"]["rows"]
    assert len(rows) == 4
    assert all(row["status"] == "WAITING_REVIEW" for row in rows)
    assert all(row["auto_publish"] == "false" for row in rows)
    assert all(row["canary_id"].startswith("canary_fresh_") for row in rows)


def test_unsafe_queue_evidence_is_ignored() -> None:
    direct, clips, queue, permissions = _fixture()
    unsafe = dict(queue[0])
    unsafe["queue_id"] = "unsafe_evidence"
    unsafe["repost_prohibited"] = "true"
    unsafe["updated_at"] = "9999-01-01T00:00:00+00:00"
    queue[0] = {
        "queue_id": "safe_incomplete",
        "account_id": "night_scout",
        "content_route": "direct_reference_media",
        "source_post_id": "sp_night_scout",
        "status": "WAITING_REVIEW",
    }
    queue.append(unsafe)
    report = integration.build_production_plan(
        direct_selections=direct,
        clip_selections=clips,
        queue_rows=queue,
        permissions=permissions,
        permission_checker=_permission,
        planner=planner.build_plan,
        candidate_validator=planner.candidate_blockers,
    )
    selected = report["selected"]["night_scout"]["direct_reference_media"]
    assert selected["evidence_queue_id"] == "safe_incomplete"
    assert report["activation_plan_status"] == "BLOCKED"


def test_missing_permission_fails_closed() -> None:
    direct, clips, queue, permissions = _fixture()
    permissions = [
        row
        for row in permissions
        if row["permission_id"] != "perm_clip_liver_manager"
    ]
    report = integration.build_production_plan(
        direct_selections=direct,
        clip_selections=clips,
        queue_rows=queue,
        permissions=permissions,
        permission_checker=_permission,
        planner=planner.build_plan,
        candidate_validator=planner.candidate_blockers,
    )
    assert report["candidate_count"] == 4
    assert report["activation_plan_status"] == "BLOCKED"
    blockers = [
        blocker
        for failure in report["activation_plan"]["failures"]
        for blocker in failure["blockers"]
    ]
    assert "permission_evidence_missing" in blockers
    assert "permission_status_not_approved" in blockers


def test_safety_guard_detects_enabled_gates() -> None:
    assert integration.safety_blockers({}) == []
    assert integration.safety_blockers({"PUBLISH_ENABLED": "true"}) == [
        "PUBLISH_ENABLED=true"
    ]


def test_inputs_are_not_mutated() -> None:
    direct, clips, queue, permissions = _fixture()
    before = deepcopy((direct, clips, queue, permissions))
    integration.build_production_plan(
        direct_selections=direct,
        clip_selections=clips,
        queue_rows=queue,
        permissions=permissions,
        permission_checker=_permission,
        planner=planner.build_plan,
        candidate_validator=planner.candidate_blockers,
    )
    assert (direct, clips, queue, permissions) == before


def test_direct_selection_skips_candidate_without_active_ledger_permission() -> None:
    direct, _clips, _queue, permissions = _fixture()
    valid = direct["night_scout"]
    invalid = (
        {
            "source_post_id": "sp_without_permission",
            "source_id": "src_without_permission",
        },
        {
            "media_asset_id": "ma_without_permission",
            "storage_url": "https://media.invalid/no-permission.mp4",
            "media_type": "video",
        },
        {"source_id": "src_without_permission"},
    )

    selected, rejected = integration.select_permissioned_direct_candidate(
        [invalid, valid],
        permissions=permissions,
        account_id="night_scout",
        permission_checker=_permission,
    )

    assert selected == valid
    assert rejected == [
        "sp_without_permission:active_direct_permission_missing"
    ]


def test_present_candidates_are_diagnosed_when_other_slots_are_missing() -> None:
    direct, clips, queue, permissions = _fixture()
    clips["night_scout"] = None
    report = integration.build_production_plan(
        direct_selections=direct,
        clip_selections=clips,
        queue_rows=queue,
        permissions=permissions,
        permission_checker=_permission,
        planner=planner.build_plan,
        candidate_validator=planner.candidate_blockers,
    )
    assert report["activation_plan_status"] == "BLOCKED"
    diagnostics = report["candidate_diagnostics"]
    assert len(diagnostics) == 3
    liver_clip = next(
        row for row in diagnostics
        if row["account_id"] == "liver_manager"
        and row["content_route"] == "approved_source_clip"
    )
    assert liver_clip["blockers"] == []


if __name__ == "__main__":
    tests = (
        test_complete_plan_is_review_only,
        test_unsafe_queue_evidence_is_ignored,
        test_missing_permission_fails_closed,
        test_safety_guard_detects_enabled_gates,
        test_inputs_are_not_mutated,
        test_direct_selection_skips_candidate_without_active_ledger_permission,
        test_present_candidates_are_diagnosed_when_other_slots_are_missing,
    )
    for test in tests:
        test()
    print(f"PASS {len(tests)} tests")
