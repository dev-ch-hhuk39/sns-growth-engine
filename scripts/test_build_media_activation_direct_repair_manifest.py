#!/usr/bin/env python3
"""Pure contracts for the Direct media activation repair manifest builder."""

from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

MODULE_PATH = Path(__file__).with_name("build_media_activation_direct_repair_manifest.py")
spec = importlib.util.spec_from_file_location("direct_repair_manifest", MODULE_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def candidate(
    account_id: str,
    *,
    source_post_id: str,
    permission: bool,
    status: str = "SOURCE_REPAIR_REQUIRED",
    repair_blockers: list[str] | None = None,
    hard_blockers: list[str] | None = None,
    blockers: list[str] | None = None,
    permission_scope_missing: list[str] | None = None,
    external_operations: list[Any] | None = None,
) -> dict[str, Any]:
    return {
        "account_id": account_id,
        "content_route": mod.ROUTE,
        "candidate_status": status,
        "candidate_score": 40.0,
        "source_post_id": source_post_id,
        "source_id": f"src_{source_post_id}",
        "source_url": f"https://www.threads.com/@creator/post/{source_post_id}",
        "platform": "threads",
        "permission_id": f"perm_{source_post_id}" if permission else "",
        "permission_active": permission,
        "permission_scope_missing": (
            permission_scope_missing
            if permission_scope_missing is not None
            else ([] if permission else ["active_permission_missing"])
        ),
        "source_text": {"hash": f"hash_{source_post_id}"},
        "repair_blockers": repair_blockers or [],
        "hard_blockers": hard_blockers or [],
        "blockers": blockers if blockers is not None else [
            *(repair_blockers or []),
            *(hard_blockers or []),
        ],
        "external_operations": external_operations or [],
    }


def inventory(
    night_candidates: list[dict[str, Any]] | None = None,
    liver_candidates: list[dict[str, Any]] | None = None,
    *,
    night_recommended: str = "sp_night",
    liver_recommended: str = "sp_liver",
) -> dict[str, Any]:
    return {
        "status": "BLOCKED_SOURCE_OR_PERMISSION_REPAIR_REQUIRED",
        "read_status": "READ_ONLY_COMPLETE",
        "slots": [
            {
                "account_id": "night_scout",
                "content_route": mod.ROUTE,
                "route_status": "EXISTING_SOURCE_REPAIR_REQUIRED",
                "recommended_candidate_id": night_recommended,
            },
            {
                "account_id": "liver_manager",
                "content_route": mod.ROUTE,
                "route_status": "EXISTING_SOURCE_REPAIR_REQUIRED",
                "recommended_candidate_id": liver_recommended,
            },
        ],
        "candidates": {
            "night_scout": {
                mod.ROUTE: night_candidates if night_candidates is not None else [
                    candidate(
                        "night_scout",
                        source_post_id="sp_night",
                        permission=False,
                        repair_blockers=[
                            "direct_media_evidence_missing",
                            "spm_night:media_not_uploaded",
                            "spm_night:media_understanding_empty",
                            "spm_night:media_understanding_not_pass",
                            "spm_night:persisted_asset_link_missing",
                        ],
                    )
                ]
            },
            "liver_manager": {
                mod.ROUTE: liver_candidates if liver_candidates is not None else [
                    candidate(
                        "liver_manager",
                        source_post_id="sp_liver",
                        permission=True,
                        repair_blockers=[
                            "direct_media_evidence_missing",
                            "spm_liver:media_not_uploaded",
                            "spm_liver:media_understanding_empty",
                            "spm_liver:media_understanding_not_pass",
                            "spm_liver:persisted_asset_link_missing",
                        ],
                    )
                ]
            },
        },
        "planned_external_operations": [],
        "safety": {
            "production_write": False,
            "sheets_write": False,
            "permission_mutation": False,
            "caption_generation": False,
            "evidence_mutation": False,
            "media_download": False,
            "media_cut": False,
            "media_upload": False,
            "queue_write": False,
            "ready_transition": False,
            "workflow_dispatch": False,
            "sns_post": False,
        },
    }


def manifests_by_account(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["account_id"]: row for row in report["manifests"]}


def test_safety_blockers():
    assert mod.safety_blockers({"ALLOW_MEDIA_POSTS": "true"}) == ["ALLOW_MEDIA_POSTS=true"]
    assert mod.safety_blockers({}) == []


def test_exactly_two_direct_manifests():
    report = mod.build_direct_repair_manifest(inventory())
    assert report["manifest_route"] == mod.ROUTE
    assert report["manifest_count"] == 2
    assert [row["account_id"] for row in report["manifests"]] == list(mod.ACCOUNTS)


def test_night_permission_gate_blocks_media_repair():
    report = mod.build_direct_repair_manifest(inventory())
    row = manifests_by_account(report)["night_scout"]
    assert row["manifest_status"] == "HUMAN_PERMISSION_REVIEW_REQUIRED_BEFORE_REPAIR"
    assert row["permission_gate"]["media_repair_may_begin"] is False
    assert row["permission_gate"]["source_permission_blockers"] == ["active_permission_missing"]
    assert row["permission_gate"]["missing_or_unverified_flags"] == list(mod.DIRECT_PERMISSION_FLAGS)
    assert row["review_handoff"]["next_stage"] == "HUMAN_PERMISSION_REVIEW"
    assert all(step["status"] == "BLOCKED_BY_PERMISSION_GATE" for step in row["repair_steps"])


def test_liver_repair_spec_is_reviewable_but_not_executable():
    report = mod.build_direct_repair_manifest(inventory())
    row = manifests_by_account(report)["liver_manager"]
    assert row["manifest_status"] == "EVIDENCE_REPAIR_SPEC_READY_FOR_HUMAN_REVIEW"
    assert row["permission_gate"]["media_repair_may_begin"] is True
    assert all(step["status"] == "REVIEWABLE_AFTER_PERMISSION" for step in row["repair_steps"])
    assert all(step["execution_allowed"] is False for step in row["repair_steps"])
    assert all(step["executable_command"] == "" for step in row["repair_steps"])


def test_upload_and_understanding_repairs_are_described():
    report = mod.build_direct_repair_manifest(inventory())
    row = manifests_by_account(report)["liver_manager"]
    kinds = {step["kind"] for step in row["repair_steps"]}
    assert "PERSISTED_MEDIA_UPLOAD_EVIDENCE_REPAIR" in kinds
    assert "PERSISTED_ASSET_LINK_REPAIR" in kinds
    assert "MEDIA_UNDERSTANDING_CONTENT_REPAIR" in kinds
    assert "MEDIA_UNDERSTANDING_STATUS_REPAIR" in kinds
    assert "DIRECT_MEDIA_EVIDENCE_REPAIR" in kinds


def test_synthetic_recommended_candidate_is_rejected():
    synthetic = candidate(
        "night_scout",
        source_post_id="sp_synthetic",
        permission=True,
        status="EXCLUDED",
        hard_blockers=["synthetic_source_forbidden"],
    )
    real = candidate(
        "night_scout",
        source_post_id="sp_real",
        permission=False,
        repair_blockers=["spm_real:media_not_uploaded"],
    )
    report = mod.build_direct_repair_manifest(
        inventory(
            night_candidates=[synthetic, real],
            night_recommended="sp_synthetic",
        )
    )
    row = manifests_by_account(report)["night_scout"]
    assert row["selected_candidate"]["source_post_id"] == "sp_real"
    assert row["rejected_candidates"][0]["candidate_id"] == "sp_synthetic"


def test_hard_blocked_candidate_is_rejected():
    blocked = candidate(
        "night_scout",
        source_post_id="sp_long",
        permission=True,
        hard_blockers=["spm_long:video_duration_above_direct_limit"],
    )
    report = mod.build_direct_repair_manifest(
        inventory(night_candidates=[blocked], night_recommended="sp_long")
    )
    row = manifests_by_account(report)["night_scout"]
    assert row["manifest_status"] == "NEW_ELIGIBLE_DIRECT_SOURCE_REQUIRED"
    assert row["selected_candidate"]["source_post_id"] == ""
    assert row["review_handoff"]["next_stage"] == "ACQUIRE_NEW_ELIGIBLE_DIRECT_SOURCE"


def test_already_used_candidate_is_rejected():
    used = candidate(
        "night_scout",
        source_post_id="sp_used",
        permission=True,
        blockers=["ma_used:already_used"],
    )
    report = mod.build_direct_repair_manifest(
        inventory(night_candidates=[used], night_recommended="sp_used")
    )
    row = manifests_by_account(report)["night_scout"]
    assert row["manifest_status"] == "NEW_ELIGIBLE_DIRECT_SOURCE_REQUIRED"


def test_external_operation_candidate_is_rejected():
    unsafe_candidate = candidate(
        "night_scout",
        source_post_id="sp_unsafe",
        permission=True,
        external_operations=[{"command": "download"}],
    )
    report = mod.build_direct_repair_manifest(
        inventory(night_candidates=[unsafe_candidate], night_recommended="sp_unsafe")
    )
    row = manifests_by_account(report)["night_scout"]
    assert row["manifest_status"] == "NEW_ELIGIBLE_DIRECT_SOURCE_REQUIRED"


def test_permission_scope_gap_blocks_repair():
    scoped = candidate(
        "night_scout",
        source_post_id="sp_scope",
        permission=True,
        permission_scope_missing=["allow_cloudinary_storage"],
        repair_blockers=["spm_scope:media_not_uploaded"],
    )
    report = mod.build_direct_repair_manifest(
        inventory(night_candidates=[scoped], night_recommended="sp_scope")
    )
    row = manifests_by_account(report)["night_scout"]
    assert row["permission_gate"]["status"] == "BLOCKED_HUMAN_DECISION_REQUIRED"
    assert row["permission_gate"]["missing_or_unverified_flags"] == ["allow_cloudinary_storage"]


def test_no_repair_blockers_routes_to_review_evidence_builder():
    ready = candidate(
        "liver_manager",
        source_post_id="sp_ready",
        permission=True,
        status="READY_FOR_REVIEW_EVIDENCE",
    )
    report = mod.build_direct_repair_manifest(
        inventory(liver_candidates=[ready], liver_recommended="sp_ready")
    )
    row = manifests_by_account(report)["liver_manager"]
    assert row["manifest_status"] == "NO_REPAIR_REQUIRED_RUN_REVIEW_EVIDENCE_BUILDER"
    assert row["repair_steps"] == []
    assert row["review_handoff"]["next_stage"] == "RUN_REVIEW_EVIDENCE_BUILDER_READ_ONLY"


def test_unknown_repair_blocker_is_preserved_generically():
    unknown = candidate(
        "liver_manager",
        source_post_id="sp_unknown",
        permission=True,
        repair_blockers=["spm_unknown:new_future_blocker"],
    )
    report = mod.build_direct_repair_manifest(
        inventory(liver_candidates=[unknown], liver_recommended="sp_unknown")
    )
    step = manifests_by_account(report)["liver_manager"]["repair_steps"][0]
    assert step["kind"] == "SOURCE_EVIDENCE_REPAIR_REVIEW"
    assert step["source_blocker"] == "spm_unknown:new_future_blocker"


def test_string_permission_true_does_not_pass_gate():
    source = candidate(
        "liver_manager",
        source_post_id="sp_string_permission",
        permission=True,
        repair_blockers=["spm_string:media_not_uploaded"],
    )
    source["permission_active"] = "true"
    report = mod.build_direct_repair_manifest(
        inventory(liver_candidates=[source], liver_recommended="sp_string_permission")
    )
    row = manifests_by_account(report)["liver_manager"]
    assert row["permission_gate"]["status"] == "BLOCKED_HUMAN_DECISION_REQUIRED"
    assert row["permission_gate"]["active_permission_present"] is False


def test_missing_direct_slot_fails_closed():
    source = inventory()
    source["slots"] = [
        row
        for row in source["slots"]
        if row["account_id"] != "night_scout"
    ]
    try:
        mod.build_direct_repair_manifest(source)
    except ValueError as exc:
        assert str(exc) == "inventory_direct_slots_missing:night_scout"
    else:
        raise AssertionError("expected ValueError")


def test_duplicate_direct_slot_fails_closed():
    source = inventory()
    source["slots"].append(deepcopy(source["slots"][0]))
    try:
        mod.build_direct_repair_manifest(source)
    except ValueError as exc:
        assert str(exc) == "inventory_direct_slots_duplicated:night_scout"
    else:
        raise AssertionError("expected ValueError")


def test_mismatched_candidate_account_fails_closed():
    source = inventory()
    source["candidates"]["night_scout"][mod.ROUTE][0]["account_id"] = "liver_manager"
    try:
        mod.build_direct_repair_manifest(source)
    except ValueError as exc:
        assert str(exc) == (
            "inventory_direct_candidate_account_mismatch:"
            "night_scout:liver_manager"
        )
    else:
        raise AssertionError("expected ValueError")


def test_all_ready_report_routes_to_review_evidence():
    night = candidate(
        "night_scout",
        source_post_id="sp_night_ready",
        permission=True,
        status="READY_FOR_REVIEW_EVIDENCE",
    )
    liver = candidate(
        "liver_manager",
        source_post_id="sp_liver_ready",
        permission=True,
        status="READY_FOR_REVIEW_EVIDENCE",
    )
    report = mod.build_direct_repair_manifest(
        inventory(
            night_candidates=[night],
            liver_candidates=[liver],
            night_recommended="sp_night_ready",
            liver_recommended="sp_liver_ready",
        )
    )
    assert report["manifest_route"] == mod.ROUTE
    assert report["status"] == "DIRECT_SOURCES_READY_FOR_REVIEW_EVIDENCE"
    assert report["review_evidence_ready_accounts"] == list(mod.ACCOUNTS)


def test_deterministic_report_and_hashes():
    source = inventory()
    first = mod.build_direct_repair_manifest(source)
    second = mod.build_direct_repair_manifest(deepcopy(source))
    assert first == second
    assert first["report_hash"] == second["report_hash"]
    assert [row["manifest_hash"] for row in first["manifests"]] == [
        row["manifest_hash"] for row in second["manifests"]
    ]


def test_no_executable_operations_anywhere():
    report = mod.build_direct_repair_manifest(inventory())
    assert report["planned_external_operations"] == []
    assert report["executable_commands"] == []
    assert all(value is False for value in report["safety"].values())
    for row in report["manifests"]:
        assert row["external_operations"] == []
        assert row["executable_commands"] == []
        assert row["review_handoff"]["automatic_execution"] is False
        assert row["review_handoff"]["queue_creation_allowed"] is False
        assert row["review_handoff"]["ready_transition_allowed"] is False


def test_inventory_external_operations_fail_closed():
    source = inventory()
    source["planned_external_operations"] = ["unsafe"]
    try:
        mod.build_direct_repair_manifest(source)
    except ValueError as exc:
        assert str(exc) == "inventory_planned_external_operations_present"
    else:
        raise AssertionError("expected ValueError")


def test_inventory_safety_fail_closed():
    source = inventory()
    source["safety"]["media_upload"] = True
    try:
        mod.build_direct_repair_manifest(source)
    except ValueError as exc:
        assert "inventory_safety_not_false" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_inventory_read_status_fail_closed():
    source = inventory()
    source["read_status"] = "PARTIAL"
    try:
        mod.build_direct_repair_manifest(source)
    except ValueError as exc:
        assert str(exc) == "inventory_not_read_only_complete"
    else:
        raise AssertionError("expected ValueError")


def main() -> None:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
    print(f"PASS {len(tests)} tests")


if __name__ == "__main__":
    main()
