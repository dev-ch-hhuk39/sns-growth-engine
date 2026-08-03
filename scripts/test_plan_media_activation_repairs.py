#!/usr/bin/env python3
"""Focused tests for the read-only media activation repair planner."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).with_name("plan_media_activation_repairs.py")
SPEC = importlib.util.spec_from_file_location("plan_media_activation_repairs", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _source_missing(account: str, route: str, reasons: list[str]) -> dict[str, Any]:
    return {
        "account_id": account,
        "content_route": route,
        "status": "SOURCE_MISSING",
        "selection_blocked_reasons": reasons,
        "candidate_blockers": [],
        "semantic_evidence": {"match_type": "NONE", "joinable": False},
    }


def _quality_slot(
    account: str,
    route: str,
    *,
    hash_status: str = "NO_PUBLIC_TEXT",
    public_present: bool = False,
) -> dict[str, Any]:
    return {
        "account_id": account,
        "content_route": route,
        "status": "QUALITY_EVIDENCE_INCOMPLETE",
        "source_post_id": "sp_lm" if route == "direct_reference_media" else "",
        "source_video_id": "sv_lm" if route == "approved_source_clip" else "",
        "clip_candidate_id": "clip_lm" if route == "approved_source_clip" else "",
        "media_asset_id": "ma_lm",
        "public_post_text_present": public_present,
        "candidate_blockers": ["quality_gate_version_invalid"],
        "semantic_evidence": {
            "match_type": "EXACT_SOURCE_POST" if route == "direct_reference_media" else "EXACT_CLIP",
            "status": "BLOCKED",
            "public_post_hash_status": hash_status,
            "joinable": False,
        },
    }


def _audit(
    night_direct: dict[str, Any] | None = None,
    night_clip: dict[str, Any] | None = None,
    liver_direct: dict[str, Any] | None = None,
    liver_clip: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "status": "READ_ONLY_COMPLETE",
        "audit_status": "BLOCKED",
        "slots": [
            night_direct or _source_missing("night_scout", "direct_reference_media", []),
            night_clip or _source_missing("night_scout", "approved_source_clip", []),
            liver_direct or _quality_slot("liver_manager", "direct_reference_media"),
            liver_clip or _quality_slot("liver_manager", "approved_source_clip", hash_status="MISMATCH", public_present=True),
        ],
    }


def _build(audit: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    values = {
        "source_posts": [],
        "source_post_media": [],
        "source_media_understanding": [],
        "media_permissions": [],
        "video_clip_candidates": [],
        "source_videos": [],
        "media_assets": [],
    }
    values.update(overrides)
    return MODULE.build_repair_plan(audit, **values)


def _slot(report: dict[str, Any], account: str, route: str) -> dict[str, Any]:
    return next(
        row for row in report["slots"]
        if row["account_id"] == account and row["content_route"] == route
    )


def test_direct_missing_permission_requires_human_decision() -> None:
    source_post_id = "sp_ns_ready"
    report = _build(
        _audit(
            night_direct=_source_missing(
                "night_scout",
                "direct_reference_media",
                [f"{source_post_id}:active_direct_permission_missing"],
            )
        ),
        source_posts=[{
            "source_post_id": source_post_id,
            "source_id": "src_ns",
            "target_account_id": "night_scout",
            "canonical_post_url": "https://www.threads.com/@x/post/abc",
        }],
        source_post_media=[{
            "source_post_media_id": "spm_ns",
            "source_post_id": source_post_id,
            "cloudinary_status": "UPLOADED",
            "storage_url": "https://cdn.example/a.jpg",
        }],
        source_media_understanding=[{
            "source_post_media_id": "spm_ns",
            "status": "PASS",
        }],
    )
    slot = _slot(report, "night_scout", "direct_reference_media")
    assert slot["source_options"][0]["status"] == "SOURCE_READY_PERMISSION_REVIEW_REQUIRED"
    assert "MEDIA_PERMISSION_LEDGER_DECISION" in slot["required_approvals"]
    assert slot["source_options"][0]["permission_review"]["decision_policy"] == "HUMAN_DECISION_ONLY_NO_AUTOMATIC_GRANT"


def test_direct_active_permission_removes_permission_write_approval() -> None:
    source_post_id = "sp_ns_ready"
    permission = {
        "permission_id": "perm_ns",
        "source_id": "src_ns",
        "account_id": "night_scout",
        "permission_status": "approved",
        "rights_status": "licensed",
        "evidence_reference": "contract-1",
        "allow_original_repost": "true",
    }
    report = _build(
        _audit(
            night_direct=_source_missing(
                "night_scout",
                "direct_reference_media",
                [f"{source_post_id}:active_direct_permission_missing"],
            )
        ),
        source_posts=[{
            "source_post_id": source_post_id,
            "source_id": "src_ns",
            "target_account_id": "night_scout",
        }],
        source_post_media=[{
            "source_post_media_id": "spm_ns",
            "source_post_id": source_post_id,
            "cloudinary_status": "UPLOADED",
            "storage_url": "https://cdn.example/a.jpg",
        }],
        source_media_understanding=[{"source_post_media_id": "spm_ns", "status": "PASS"}],
        media_permissions=[permission],
    )
    slot = _slot(report, "night_scout", "direct_reference_media")
    assert slot["source_options"][0]["status"] == "SOURCE_READY_ACTIVE_PERMISSION_PRESENT"
    assert "MEDIA_PERMISSION_LEDGER_DECISION" not in slot["required_approvals"]


def test_direct_incomplete_understanding_is_lower_priority() -> None:
    ready_id = "sp_ns_ready"
    incomplete_id = "sp_ns_incomplete"
    report = _build(
        _audit(
            night_direct=_source_missing(
                "night_scout",
                "direct_reference_media",
                [
                    f"{ready_id}:active_direct_permission_missing",
                    f"{incomplete_id}:media_content_understanding_missing",
                ],
            )
        ),
        source_posts=[
            {"source_post_id": ready_id, "source_id": "src_ready", "target_account_id": "night_scout"},
            {"source_post_id": incomplete_id, "source_id": "src_bad", "target_account_id": "night_scout"},
        ],
        source_post_media=[
            {"source_post_media_id": "spm_ready", "source_post_id": ready_id, "cloudinary_status": "UPLOADED", "storage_url": "https://cdn.example/ready.jpg"},
            {"source_post_media_id": "spm_bad", "source_post_id": incomplete_id, "cloudinary_status": "UPLOADED", "storage_url": "https://cdn.example/bad.jpg"},
        ],
        source_media_understanding=[{"source_post_media_id": "spm_ready", "status": "PASS"}],
    )
    options = _slot(report, "night_scout", "direct_reference_media")["source_options"]
    assert options[0]["source_post_id"] == ready_id
    assert options[0]["preferred"] is True
    assert options[1]["status"] == "CONTENT_UNDERSTANDING_OR_UPLOAD_REPAIR_REQUIRED"


def test_not_uploaded_clip_plans_upload_without_execution() -> None:
    asset_id = "ma_clip_01"
    clip_id = "clip_01"
    source_video_id = "sv_01"
    report = _build(
        _audit(
            night_clip=_source_missing(
                "night_scout",
                "approved_source_clip",
                [f"{asset_id}:not_uploaded"],
            )
        ),
        media_assets=[{
            "media_id": asset_id,
            "account_id": "night_scout",
            "video_clip_id": clip_id,
            "local_path": "/tmp/clip.mp4",
            "upload_status": "PENDING",
        }],
        video_clip_candidates=[{
            "clip_candidate_id": clip_id,
            "source_video_id": source_video_id,
            "cut_status": "DONE",
            "local_clip_path": "/tmp/clip.mp4",
            "transcript_grounded": "true",
            "start_seconds": "1",
            "end_seconds": "20",
        }],
        source_videos=[{
            "source_video_id": source_video_id,
            "source_id": "src_clip",
            "account_id": "night_scout",
            "download_status": "DOWNLOADED",
            "local_path": "/tmp/source.mp4",
            "canonical_video_url": "https://youtube.com/watch?v=abcdefghijk",
        }],
        media_permissions=[{
            "permission_id": "perm_clip",
            "source_id": "src_clip",
            "account_id": "night_scout",
            "permission_status": "approved",
            "rights_status": "approved_creator_clip",
            "evidence_reference": "owner-1",
            "allow_clip_repost": "true",
        }],
    )
    slot = _slot(report, "night_scout", "approved_source_clip")
    option = slot["source_options"][0]
    assert option["required_media_operations"] == ["CLOUD_STORAGE_UPLOAD_REQUIRED"]
    assert "CLOUD_MEDIA_UPLOAD" in slot["required_approvals"]
    assert report["safety"]["media_upload"] is False


def test_unprepared_clip_derives_download_cut_and_upload() -> None:
    report = _build(
        _audit(
            night_clip=_source_missing(
                "night_scout",
                "approved_source_clip",
                ["ma_clip_03:not_uploaded"],
            )
        ),
        media_assets=[{"media_id": "ma_clip_03", "account_id": "night_scout", "video_clip_id": "clip_03"}],
        video_clip_candidates=[{"clip_candidate_id": "clip_03", "source_video_id": "sv_03"}],
        source_videos=[{"source_video_id": "sv_03", "source_id": "src_03"}],
    )
    option = _slot(report, "night_scout", "approved_source_clip")["source_options"][0]
    assert option["required_media_operations"] == [
        "VIDEO_DOWNLOAD_REQUIRED",
        "CLIP_CUT_REQUIRED",
        "CLOUD_STORAGE_UPLOAD_REQUIRED",
    ]


def test_quarantined_clip_is_excluded() -> None:
    report = _build(
        _audit(
            night_clip=_source_missing(
                "night_scout",
                "approved_source_clip",
                ["ma_clip_02:clip_quarantined"],
            )
        ),
        media_assets=[{"media_id": "ma_clip_02", "account_id": "night_scout", "video_clip_id": "clip_02"}],
        video_clip_candidates=[{
            "clip_candidate_id": "clip_02",
            "source_video_id": "sv_02",
            "clip_status": "QUARANTINED",
            "quarantine_reason": "repeated_failure",
        }],
        source_videos=[{"source_video_id": "sv_02", "source_id": "src_02"}],
    )
    slot = _slot(report, "night_scout", "approved_source_clip")
    assert slot["source_options"] == []
    assert slot["excluded_options"][0]["status"] == "DO_NOT_USE_QUARANTINED"


def test_liver_direct_requires_route_and_visual_evidence_builders() -> None:
    report = _build(_audit())
    slot = _slot(report, "liver_manager", "direct_reference_media")
    assert slot["ordered_steps"][0] == "GENERATE_SOURCE_PRESERVING_CAPTION_FROM_EXACT_PARENT_POST"
    assert "VISUAL_PLAN_V1_EVIDENCE_ENRICHER_REQUIRED" in slot["code_gaps"]
    assert slot["completion_contract"]["candidate_status"] == "WAITING_REVIEW"
    assert slot["completion_contract"]["ready_transition"] is False


def test_clip_hash_mismatch_forbids_old_alignment_reuse() -> None:
    report = _build(_audit())
    slot = _slot(report, "liver_manager", "approved_source_clip")
    assert slot["ordered_steps"][0] == "DO_NOT_REUSE_MISMATCHED_PUBLIC_POST_ALIGNMENT"
    assert slot["evidence_diagnostics"]["public_post_hash_status"] == "MISMATCH"
    assert slot["evidence_diagnostics"]["alignment_joinable"] is False


def test_all_complete_slots_need_no_repair() -> None:
    complete_slots = [
        {
            "account_id": account,
            "content_route": route,
            "status": "QUALITY_COMPLETE",
        }
        for account in MODULE.ACCOUNTS
        for route in MODULE.ROUTES
    ]
    report = _build({"slots": complete_slots})
    assert report["repair_status"] == "READY_FOR_REVIEW"
    assert report["repair_required_count"] == 0
    assert report["approval_required_slot_count"] == 0


def test_unsafe_environment_is_blocked() -> None:
    assert MODULE.safety_blockers({"PUBLISH_ENABLED": "true"}) == ["PUBLISH_ENABLED=true"]
    assert MODULE.safety_blockers({"PUBLISH_ENABLED": "false"}) == []


def test_report_is_planning_only() -> None:
    report = _build(_audit())
    assert report["slot_count"] == 4
    assert all(value is False for value in report["safety"].values())
    encoded = str(report)
    assert "auto_publish': True" not in encoded
    assert "candidate_status': 'READY'" not in encoded


def main() -> int:
    tests = [
        value for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
    print(f"PASS {len(tests)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
