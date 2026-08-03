#!/usr/bin/env python3
"""Contracts for exact Direct media repair and its manual workflow."""

from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    Path(__file__).with_name(
        "run_media_activation_direct_repair.py"
    )
)
WORKFLOW_PATH = (
    ROOT
    / ".github"
    / "workflows"
    / "media-activation-direct-repair.yml"
)

spec = importlib.util.spec_from_file_location(
    "exact_direct_repair",
    MODULE_PATH,
)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


def manifest_report(
    *,
    account_id: str = "liver_manager",
    source_post_id: str = "sp_liver",
    source_post_media_id: str = "spm_liver_0",
    manifest_hash: str = "a" * 64,
    permission: bool = True,
    status: str = (
        "EVIDENCE_REPAIR_SPEC_READY_FOR_HUMAN_REVIEW"
    ),
) -> dict[str, Any]:
    manifests = []
    for current in mod.ACCOUNTS:
        selected_id = (
            source_post_id
            if current == account_id
            else f"sp_{current}"
        )
        rows = (
            [
                {
                    "step_id": "repair-01",
                    "kind": (
                        "PERSISTED_MEDIA_UPLOAD_EVIDENCE_REPAIR"
                    ),
                    "target_id": source_post_media_id,
                    "status": "REVIEWABLE_AFTER_PERMISSION",
                    "execution_allowed": False,
                    "executable_command": "",
                }
            ]
            if current == account_id
            else []
        )
        manifests.append(
            {
                "account_id": current,
                "content_route": mod.ROUTE,
                "manifest_hash": (
                    manifest_hash
                    if current == account_id
                    else "b" * 64
                ),
                "manifest_status": (
                    status
                    if current == account_id
                    else (
                        "HUMAN_PERMISSION_REVIEW_REQUIRED_"
                        "BEFORE_REPAIR"
                    )
                ),
                "selected_candidate": {
                    "source_post_id": selected_id,
                },
                "permission_gate": {
                    "status": (
                        "PASS_ACTIVE_PERMISSION"
                        if current == account_id and permission
                        else "BLOCKED_HUMAN_DECISION_REQUIRED"
                    ),
                    "active_permission_present": (
                        current == account_id and permission
                    ),
                    "media_repair_may_begin": (
                        current == account_id and permission
                    ),
                    "missing_or_unverified_flags": [],
                },
                "repair_steps": rows,
                "external_operations": [],
                "executable_commands": [],
            }
        )
    return {
        "read_status": "READ_ONLY_COMPLETE",
        "manifest_route": mod.ROUTE,
        "manifests": manifests,
        "planned_external_operations": [],
        "executable_commands": [],
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


def expect_value_error(fn, message: str) -> None:
    try:
        fn()
    except ValueError as exc:
        assert str(exc) == message
    else:
        raise AssertionError(
            f"expected ValueError: {message}"
        )


def test_dry_run_env_requires_all_heavy_flags_false():
    blockers = mod.safety_blockers(
        {
            "ALLOW_VIDEO_DOWNLOAD": "true",
            "ALLOW_CLOUDINARY_UPLOAD": "false",
            "ALLOW_LOCAL_TRANSCRIPTION": "false",
        },
        apply=False,
    )
    assert blockers == [
        "ALLOW_VIDEO_DOWNLOAD=true_in_dry_run"
    ]


def test_apply_env_requires_exact_repair_flags():
    blockers = mod.safety_blockers(
        {
            "ALLOW_VIDEO_DOWNLOAD": "true",
            "ALLOW_CLOUDINARY_UPLOAD": "false",
            "ALLOW_LOCAL_TRANSCRIPTION": "true",
        },
        apply=True,
    )
    assert blockers == [
        "ALLOW_CLOUDINARY_UPLOAD=not_true"
    ]


def test_posting_and_cut_flags_are_always_blocked():
    blockers = mod.safety_blockers(
        {
            "PUBLISH_ENABLED": "true",
            "ALLOW_VIDEO_CUT": "true",
            "ALLOW_VIDEO_DOWNLOAD": "true",
            "ALLOW_CLOUDINARY_UPLOAD": "true",
            "ALLOW_LOCAL_TRANSCRIPTION": "true",
        },
        apply=True,
    )
    assert blockers == [
        "PUBLISH_ENABLED=true",
        "ALLOW_VIDEO_CUT=true",
    ]


def test_exact_manifest_target_passes():
    report = manifest_report()
    row = mod.validate_repair_target(
        report,
        account_id="liver_manager",
        source_post_id="sp_liver",
        source_post_media_id="spm_liver_0",
        expected_manifest_hash="a" * 64,
    )
    assert row["account_id"] == "liver_manager"


def test_manifest_hash_mismatch_fails_closed():
    expect_value_error(
        lambda: mod.validate_repair_target(
            manifest_report(),
            account_id="liver_manager",
            source_post_id="sp_liver",
            source_post_media_id="spm_liver_0",
            expected_manifest_hash="c" * 64,
        ),
        "manifest_hash_mismatch",
    )


def test_permission_blocked_manifest_is_rejected():
    expect_value_error(
        lambda: mod.validate_repair_target(
            manifest_report(permission=False),
            account_id="liver_manager",
            source_post_id="sp_liver",
            source_post_media_id="spm_liver_0",
            expected_manifest_hash="a" * 64,
        ),
        "active_permission_required",
    )


def test_wrong_source_post_is_rejected():
    expect_value_error(
        lambda: mod.validate_repair_target(
            manifest_report(),
            account_id="liver_manager",
            source_post_id="sp_other",
            source_post_media_id="spm_liver_0",
            expected_manifest_hash="a" * 64,
        ),
        "selected_source_post_id_mismatch",
    )


def test_media_id_must_exist_in_manifest_steps():
    expect_value_error(
        lambda: mod.validate_repair_target(
            manifest_report(),
            account_id="liver_manager",
            source_post_id="sp_liver",
            source_post_media_id="spm_other",
            expected_manifest_hash="a" * 64,
        ),
        "source_post_media_not_in_repair_manifest",
    )


def test_manifest_external_operations_are_rejected():
    report = manifest_report()
    report["planned_external_operations"] = ["unsafe"]
    expect_value_error(
        lambda: mod.validate_repair_target(
            report,
            account_id="liver_manager",
            source_post_id="sp_liver",
            source_post_media_id="spm_liver_0",
            expected_manifest_hash="a" * 64,
        ),
        "manifest_external_operations_present",
    )


def test_protected_snapshot_is_deterministic():
    first = mod.protected_snapshot(
        {
            "queue": [
                {"queue_id": "q2"},
                {"queue_id": "q1"},
            ],
            "posted_results": [
                {"result_id": "r1"},
            ],
        }
    )
    second = mod.protected_snapshot(
        {
            "queue": [
                {"queue_id": "q1"},
                {"queue_id": "q2"},
            ],
            "posted_results": [
                {"result_id": "r1"},
            ],
        }
    )
    assert first == second


def test_protected_state_change_is_detected():
    before = mod.protected_snapshot(
        {
            "queue": [{"queue_id": "q1"}],
            "posted_results": [],
        }
    )
    after = mod.protected_snapshot(
        {
            "queue": [
                {"queue_id": "q1"},
                {"queue_id": "q2"},
            ],
            "posted_results": [],
        }
    )
    try:
        mod.assert_protected_unchanged(before, after)
    except RuntimeError as exc:
        assert str(exc) == "protected_state_changed:queue"
    else:
        raise AssertionError("expected protected-state failure")


def test_exact_source_rows_are_bound_to_account_and_parent():
    post, media = mod.resolve_exact_source_rows(
        {
            "source_posts": [
                {
                    "source_post_id": "sp_liver",
                    "source_id": "src_liver",
                    "target_account_id": "liver_manager",
                    "platform": "tiktok",
                }
            ],
            "source_post_media": [
                {
                    "source_post_media_id": "spm_liver_0",
                    "source_post_id": "sp_liver",
                    "media_type": "video",
                    "original_media_url": (
                        "https://example.com/video.mp4"
                    ),
                }
            ],
        },
        account_id="liver_manager",
        source_post_id="sp_liver",
        source_post_media_id="spm_liver_0",
    )
    assert post["source_id"] == "src_liver"
    assert media["media_type"] == "video"


def test_post_repair_rejects_remaining_target_steps():
    report = manifest_report()
    try:
        mod.validate_post_repair(
            report,
            account_id="liver_manager",
            source_post_id="sp_liver",
            source_post_media_id="spm_liver_0",
        )
    except RuntimeError as exc:
        assert str(exc).startswith(
            "target_repair_steps_remaining:"
        )
    else:
        raise AssertionError(
            "expected remaining repair-step failure"
        )


def test_post_repair_allows_other_remaining_steps():
    report = manifest_report()
    row = next(
        item
        for item in report["manifests"]
        if item["account_id"] == "liver_manager"
    )
    row["repair_steps"] = [
        {
            "kind": "OTHER_MEDIA_REPAIR",
            "target_id": "spm_other",
        }
    ]
    validated = mod.validate_post_repair(
        report,
        account_id="liver_manager",
        source_post_id="sp_liver",
        source_post_media_id="spm_liver_0",
    )
    assert validated["account_id"] == "liver_manager"


def test_ingest_json_extraction_tolerates_prefix_output():
    value = mod._extract_json_object(
        'header\n{"status":"INGESTED_BUNDLE"}\n'
    )
    assert value["status"] == "INGESTED_BUNDLE"


def test_workflow_is_manual_exact_and_non_posting():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    for input_name in (
        "account_id:",
        "source_post_id:",
        "source_post_media_id:",
        "expected_manifest_hash:",
        "confirm_repair:",
    ):
        assert input_name in workflow

    assert 'permissions:\n  contents: read' in workflow
    assert "environment: production" in workflow
    assert "cancel-in-progress: false" in workflow
    assert (
        "run_media_activation_direct_repair.py"
        in workflow
    )
    assert "--dry-run" in workflow
    assert "--apply" in workflow
    assert "--confirm-repair" in workflow
    assert (
        "github.event.inputs.confirm_repair == 'true'"
        in workflow
    )
    assert (
        "ingest_direct_reference_media.py"
        not in workflow
    )
    assert (
        "run_direct_reference_media_pipeline"
        not in workflow
    )
    assert 'PUBLISH_ENABLED: "false"' in workflow
    assert 'ALLOW_REAL_THREADS_POST: "false"' in workflow
    assert 'ALLOW_MEDIA_POSTS: "false"' in workflow
    assert 'ALLOW_REAL_THREADS_VIDEO_POST: "false"' in workflow
    assert 'ALLOW_VIDEO_CUT: "false"' in workflow
    assert 'ALLOW_TRANSCRIPTION_API: "false"' in workflow
    assert 'GITHUB_MODELS_ENABLED: "false"' in workflow
    assert 'ALLOW_VIDEO_CUT: "true"' not in workflow
    assert 'ALLOW_MEDIA_POSTS: "true"' not in workflow
    assert 'PUBLISH_ENABLED: "true"' not in workflow


def main() -> None:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test_fn in tests:
        test_fn()
    print(f"PASS {len(tests)} tests")


if __name__ == "__main__":
    main()
