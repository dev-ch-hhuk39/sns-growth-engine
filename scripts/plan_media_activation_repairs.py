#!/usr/bin/env python3
"""Build a read-only repair plan for the four media activation slots.

The planner converts the current Production audit into ordered, reviewable
repair steps. It never grants permission, generates captions, processes media,
mutates Sheets, creates queue rows, changes lifecycle status, dispatches a
workflow, or posts to an SNS.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

ACCOUNTS = ("night_scout", "liver_manager")
ROUTES = ("direct_reference_media", "approved_source_clip")
DANGEROUS_ENV = (
    "PUBLISH_ENABLED",
    "ALLOW_REAL_X_POST",
    "ALLOW_REAL_THREADS_POST",
    "ALLOW_MEDIA_POSTS",
    "ALLOW_REAL_THREADS_VIDEO_POST",
    "ALLOW_VIDEO_DOWNLOAD",
    "ALLOW_VIDEO_CUT",
    "ALLOW_CLOUDINARY_UPLOAD",
    "ALLOW_TRANSCRIPTION_API",
    "GITHUB_MODELS_ENABLED",
    "ENABLE_SENTENCE_TRANSFORMERS",
)
APPROVED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}
DIRECT_PERMISSION_FLAGS = (
    "allow_download",
    "allow_cloudinary_storage",
    "allow_original_repost",
    "allow_new_caption",
)
CLIP_PERMISSION_FLAGS = (
    "allow_download",
    "allow_cut",
    "allow_cloudinary_storage",
    "allow_clip_repost",
    "allow_new_caption",
)
PermissionChecker = Callable[..., bool]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _true(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "pass"}


def safety_blockers(environ: Mapping[str, str] | None = None) -> list[str]:
    source = os.environ if environ is None else environ
    return [f"{name}=true" for name in DANGEROUS_ENV if _true(source.get(name))]


def _id(row: Mapping[str, Any], *fields: str) -> str:
    for field in fields:
        value = _text(row.get(field))
        if value:
            return value
    return ""


def _index(rows: list[dict[str, Any]], *fields: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in rows:
        row = dict(item)
        value = _id(row, *fields)
        if value:
            result[value] = row
    return result


def _group(rows: list[dict[str, Any]], *fields: str) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for item in rows:
        row = dict(item)
        value = _id(row, *fields)
        if value:
            result.setdefault(value, []).append(row)
    return result


def _audit_slots(audit: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for item in audit.get("slots", []):
        if not isinstance(item, Mapping):
            continue
        row = dict(item)
        result[(_text(row.get("account_id")), _text(row.get("content_route")))] = row
    return result


def _reason_entities(reasons: list[str], suffix: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    marker = f":{suffix}"
    for raw in reasons:
        reason = _text(raw)
        if not reason.endswith(marker):
            continue
        entity = reason[: -len(marker)]
        if entity and entity not in seen:
            seen.add(entity)
            found.append(entity)
    return found


def _conservative_permission(
    row: Mapping[str, Any],
    *,
    account_id: str,
    operation: str,
) -> bool:
    if _text(row.get("account_id")) != account_id:
        return False
    if _text(row.get("permission_status")).lower() != "approved":
        return False
    if _text(row.get("rights_status")).lower() not in APPROVED_RIGHTS:
        return False
    if _true(row.get("revoked")) or not _text(row.get("evidence_reference")):
        return False
    field = {
        "direct": "allow_original_repost",
        "clip": "allow_clip_repost",
        "download": "allow_download",
        "upload": "allow_cloudinary_storage",
    }.get(operation, "")
    return bool(field and _true(row.get(field)))


def _active_permission(
    rows: list[dict[str, Any]],
    *,
    account_id: str,
    source_id: str,
    operation: str,
    checker: PermissionChecker | None,
) -> dict[str, Any]:
    permission_checker = checker or _conservative_permission
    candidates = [
        dict(row)
        for row in rows
        if _text(row.get("source_id")) == source_id
        and permission_checker(row, account_id=account_id, operation=operation)
    ]
    candidates.sort(
        key=lambda row: (
            _text(row.get("updated_at") or row.get("approved_at")),
            _text(row.get("permission_id")),
        ),
        reverse=True,
    )
    return candidates[0] if candidates else {}


def _permission_review(
    *,
    account_id: str,
    source_id: str,
    source_url: str,
    operation: str,
    permission: Mapping[str, Any],
) -> dict[str, Any]:
    required_flags = DIRECT_PERMISSION_FLAGS if operation == "direct" else CLIP_PERMISSION_FLAGS
    return {
        "source_id": source_id,
        "source_url": source_url,
        "operation": operation,
        "active_permission_present": bool(permission),
        "permission_id": _text(permission.get("permission_id")),
        "required_flags_for_human_review": list(required_flags),
        "decision_policy": "HUMAN_DECISION_ONLY_NO_AUTOMATIC_GRANT",
    }


def _direct_media_state(
    source_post_id: str,
    *,
    media_by_post: Mapping[str, list[dict[str, Any]]],
    understandings_by_media: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    media = [dict(row) for row in media_by_post.get(source_post_id, [])]
    understanding_pass = 0
    uploaded = 0
    for item in media:
        media_id = _id(item, "source_post_media_id", "media_asset_id", "media_id")
        understanding_rows = understandings_by_media.get(media_id, [])
        if any(_text(row.get("status")).upper() == "PASS" for row in understanding_rows):
            understanding_pass += 1
        if (
            _text(item.get("cloudinary_status") or item.get("upload_status")).upper() == "UPLOADED"
            and bool(_text(item.get("storage_url") or item.get("cloudinary_url")))
        ):
            uploaded += 1
    return {
        "media_count": len(media),
        "understanding_pass_count": understanding_pass,
        "uploaded_count": uploaded,
        "media_complete": bool(media) and understanding_pass == len(media) and uploaded == len(media),
    }


def _direct_source_options(
    slot: Mapping[str, Any],
    *,
    source_posts: list[dict[str, Any]],
    source_post_media: list[dict[str, Any]],
    source_media_understanding: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    permission_checker: PermissionChecker | None,
) -> list[dict[str, Any]]:
    account_id = _text(slot.get("account_id"))
    posts = _index(source_posts, "source_post_id")
    media_by_post = _group(source_post_media, "source_post_id")
    understandings_by_media = _group(source_media_understanding, "source_post_media_id")
    reasons = [str(value) for value in slot.get("selection_blocked_reasons", [])]
    permission_missing = _reason_entities(reasons, "active_direct_permission_missing")
    understanding_missing = _reason_entities(reasons, "media_content_understanding_missing")
    ordered_ids = permission_missing + [value for value in understanding_missing if value not in permission_missing]
    options: list[dict[str, Any]] = []

    for source_post_id in ordered_ids[:10]:
        post = posts.get(source_post_id, {})
        if post and _text(post.get("target_account_id")) not in {"", account_id}:
            continue
        source_id = _text(post.get("source_id"))
        source_url = _text(post.get("canonical_post_url") or post.get("post_url"))
        permission = _active_permission(
            permissions,
            account_id=account_id,
            source_id=source_id,
            operation="direct",
            checker=permission_checker,
        ) if source_id else {}
        media_state = _direct_media_state(
            source_post_id,
            media_by_post=media_by_post,
            understandings_by_media=understandings_by_media,
        )
        blocked_only_permission = source_post_id in permission_missing and media_state["media_complete"]
        status = (
            "SOURCE_READY_ACTIVE_PERMISSION_PRESENT"
            if blocked_only_permission and permission
            else "SOURCE_READY_PERMISSION_REVIEW_REQUIRED"
            if blocked_only_permission
            else "CONTENT_UNDERSTANDING_OR_UPLOAD_REPAIR_REQUIRED"
        )
        options.append(
            {
                "source_post_id": source_post_id,
                "source_id": source_id,
                "source_url": source_url,
                "status": status,
                "preferred": False,
                "media_state": media_state,
                "permission_review": _permission_review(
                    account_id=account_id,
                    source_id=source_id,
                    source_url=source_url,
                    operation="direct",
                    permission=permission,
                ),
            }
        )

    options.sort(
        key=lambda row: (
            0 if row["status"] == "SOURCE_READY_ACTIVE_PERMISSION_PRESENT" else 1
            if row["status"] == "SOURCE_READY_PERMISSION_REVIEW_REQUIRED" else 2,
            -int(row["media_state"]["understanding_pass_count"]),
            row["source_post_id"],
        )
    )
    if options:
        options[0]["preferred"] = True
    return options


def _is_quarantined(row: Mapping[str, Any]) -> bool:
    statuses = {
        _text(row.get("clip_status")).upper(),
        _text(row.get("reviewer_status")).upper(),
        _text(row.get("post_status")).upper(),
        _text(row.get("status")).upper(),
    }
    return bool(
        "QUARANTINED" in statuses
        or _text(row.get("quarantined_at"))
        or _text(row.get("quarantine_reason"))
    )


def _clip_operation_steps(
    *,
    clip: Mapping[str, Any],
    source_video: Mapping[str, Any],
    asset: Mapping[str, Any],
) -> list[str]:
    steps: list[str] = []
    source_local = _text(source_video.get("local_path"))
    source_downloaded = _text(source_video.get("download_status")).upper() in {"DONE", "DOWNLOADED", "COMPLETE"}
    clip_local = _text(clip.get("local_clip_path") or clip.get("local_path") or asset.get("local_path"))
    cut_done = _text(clip.get("cut_status")).upper() in {"DONE", "CUT", "COMPLETE"}
    uploaded = (
        _text(asset.get("upload_status") or asset.get("cloudinary_status")).upper() == "UPLOADED"
        and bool(_text(asset.get("storage_url") or asset.get("cloudinary_url")))
    )
    if not source_local and not source_downloaded:
        steps.append("VIDEO_DOWNLOAD_REQUIRED")
    if not clip_local and not cut_done:
        steps.append("CLIP_CUT_REQUIRED")
    if not uploaded:
        steps.append("CLOUD_STORAGE_UPLOAD_REQUIRED")
    return steps


def _clip_source_options(
    slot: Mapping[str, Any],
    *,
    video_clip_candidates: list[dict[str, Any]],
    source_videos: list[dict[str, Any]],
    media_assets: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    permission_checker: PermissionChecker | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    account_id = _text(slot.get("account_id"))
    clips = _index(video_clip_candidates, "clip_candidate_id", "clip_id")
    videos = _index(source_videos, "source_video_id")
    assets = _index(media_assets, "media_asset_id", "media_id")
    reasons = [str(value) for value in slot.get("selection_blocked_reasons", [])]
    candidate_asset_ids: list[str] = []
    for reason in reasons:
        match = re.match(r"([^:]+):(not_uploaded|clip_quarantined|already_posted|final_clip_time_range_missing)$", reason)
        if match and match.group(1) not in candidate_asset_ids:
            candidate_asset_ids.append(match.group(1))

    options: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for media_asset_id in candidate_asset_ids[:12]:
        asset = assets.get(media_asset_id, {})
        clip_id = _id(asset, "clip_candidate_id", "video_clip_id")
        clip = clips.get(clip_id, {})
        source_video_id = _id(clip, "source_video_id", "reference_post_id") or _text(asset.get("source_video_id"))
        source_video = videos.get(source_video_id, {})
        source_id = _text(source_video.get("source_id") or clip.get("source_id"))
        source_url = _text(source_video.get("canonical_video_url") or source_video.get("source_video_url") or source_video.get("source_url"))
        quarantined = _is_quarantined(clip) or reason_for_asset(reasons, media_asset_id) == "clip_quarantined"
        if quarantined:
            excluded.append(
                {
                    "media_asset_id": media_asset_id,
                    "clip_candidate_id": clip_id,
                    "source_video_id": source_video_id,
                    "status": "DO_NOT_USE_QUARANTINED",
                    "reason": _text(clip.get("quarantine_reason")) or "clip_quarantined",
                }
            )
            continue
        if not clip or not source_video:
            excluded.append(
                {
                    "media_asset_id": media_asset_id,
                    "clip_candidate_id": clip_id,
                    "source_video_id": source_video_id,
                    "status": "SOURCE_JOIN_REPAIR_REQUIRED",
                    "reason": "clip_or_source_video_missing",
                }
            )
            continue
        permission = _active_permission(
            permissions,
            account_id=account_id,
            source_id=source_id,
            operation="clip",
            checker=permission_checker,
        ) if source_id else {}
        operations = _clip_operation_steps(clip=clip, source_video=source_video, asset=asset)
        status = (
            "SOURCE_MEDIA_READY"
            if not operations and permission
            else "MEDIA_PREPARATION_APPROVAL_REQUIRED"
            if permission
            else "PERMISSION_AND_MEDIA_PREPARATION_REVIEW_REQUIRED"
        )
        options.append(
            {
                "media_asset_id": media_asset_id,
                "clip_candidate_id": clip_id,
                "source_video_id": source_video_id,
                "source_id": source_id,
                "source_url": source_url,
                "status": status,
                "preferred": False,
                "required_media_operations": operations,
                "permission_review": _permission_review(
                    account_id=account_id,
                    source_id=source_id,
                    source_url=source_url,
                    operation="clip",
                    permission=permission,
                ),
                "transcript_grounded": _true(clip.get("transcript_grounded")),
                "start_seconds": _text(clip.get("start_seconds") or clip.get("start_time")),
                "end_seconds": _text(clip.get("end_seconds") or clip.get("end_time")),
            }
        )

    options.sort(
        key=lambda row: (
            0 if row["status"] == "SOURCE_MEDIA_READY" else 1,
            0 if row["permission_review"]["active_permission_present"] else 1,
            len(row["required_media_operations"]),
            row["clip_candidate_id"],
        )
    )
    if options:
        options[0]["preferred"] = True
    return options, excluded


def reason_for_asset(reasons: list[str], media_asset_id: str) -> str:
    prefix = f"{media_asset_id}:"
    for reason in reasons:
        if reason.startswith(prefix):
            return reason[len(prefix):]
    return ""


def _approvals_for_clip_option(option: Mapping[str, Any]) -> list[str]:
    approvals: list[str] = []
    permission = option.get("permission_review", {})
    if isinstance(permission, Mapping) and not permission.get("active_permission_present"):
        approvals.append("MEDIA_PERMISSION_LEDGER_DECISION")
    mapping = {
        "VIDEO_DOWNLOAD_REQUIRED": "EXTERNAL_VIDEO_DOWNLOAD",
        "CLIP_CUT_REQUIRED": "LOCAL_CLIP_CUT",
        "CLOUD_STORAGE_UPLOAD_REQUIRED": "CLOUD_MEDIA_UPLOAD",
    }
    for step in option.get("required_media_operations", []):
        approval = mapping.get(str(step))
        if approval and approval not in approvals:
            approvals.append(approval)
    return approvals


def _base_completion_contract() -> dict[str, Any]:
    return {
        "candidate_status": "WAITING_REVIEW",
        "auto_publish": False,
        "ready_transition": False,
        "exact_source_identity_required": True,
        "permission_evidence_required": True,
        "public_validation_required": True,
        "semantic_alignment_required": True,
        "batch_topic_structure_evidence_required": True,
        "visual_evidence_required": True,
        "public_post_hash_must_match_alignment": True,
    }


def _night_direct_plan(
    slot: Mapping[str, Any],
    *,
    source_posts: list[dict[str, Any]],
    source_post_media: list[dict[str, Any]],
    source_media_understanding: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    permission_checker: PermissionChecker | None,
) -> dict[str, Any]:
    options = _direct_source_options(
        slot,
        source_posts=source_posts,
        source_post_media=source_post_media,
        source_media_understanding=source_media_understanding,
        permissions=permissions,
        permission_checker=permission_checker,
    )
    preferred = next((row for row in options if row.get("preferred")), {})
    approvals = [] if preferred.get("permission_review", {}).get("active_permission_present") else ["MEDIA_PERMISSION_LEDGER_DECISION"]
    steps = [
        "HUMAN_REVIEW_SELECTED_PARENT_POST_AND_RIGHTS",
    ]
    if approvals:
        steps.append("HUMAN_PERMISSION_LEDGER_DECISION")
    if preferred and not preferred.get("media_state", {}).get("media_complete"):
        steps.append("COMPLETE_MEDIA_UNDERSTANDING_OR_UPLOAD_EVIDENCE")
    steps.extend(
        [
            "RERUN_READ_ONLY_SOURCE_SELECTION",
            "GENERATE_SOURCE_PRESERVING_CAPTION_AND_EXACT_ALIGNMENT",
            "EVALUATE_BATCH_TOPIC_STRUCTURE_AND_VISUAL_EVIDENCE",
            "BUILD_REVIEW_ONLY_ACTIVATION_CANDIDATE",
        ]
    )
    return {
        "account_id": "night_scout",
        "content_route": "direct_reference_media",
        "status": "REQUIRES_HUMAN_PERMISSION_OR_ALTERNATIVE_SOURCE",
        "preferred_path": "REVIEW_PREPARED_PARENT_SOURCE_PERMISSION",
        "source_options": options,
        "excluded_options": [],
        "ordered_steps": steps,
        "required_approvals": approvals + ["CAPTION_AND_QUALITY_EVIDENCE_GENERATION"],
        "code_gaps": ["REVIEW_ONLY_ROUTE_EVIDENCE_BUILDER_REQUIRED"],
        "unsafe_existing_entrypoints": [
            "run_direct_reference_media_pipeline.py prepare/apply creates READY inventory",
            "run_direct_reference_media_pipeline.py publish path can post",
        ],
        "completion_contract": _base_completion_contract(),
    }


def _night_clip_plan(
    slot: Mapping[str, Any],
    *,
    video_clip_candidates: list[dict[str, Any]],
    source_videos: list[dict[str, Any]],
    media_assets: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    permission_checker: PermissionChecker | None,
) -> dict[str, Any]:
    options, excluded = _clip_source_options(
        slot,
        video_clip_candidates=video_clip_candidates,
        source_videos=source_videos,
        media_assets=media_assets,
        permissions=permissions,
        permission_checker=permission_checker,
    )
    preferred = next((row for row in options if row.get("preferred")), {})
    approvals = _approvals_for_clip_option(preferred) if preferred else []
    steps = ["SELECT_NON_QUARANTINED_EXACT_CLIP_OPTION"]
    if preferred and not preferred.get("permission_review", {}).get("active_permission_present"):
        steps.append("HUMAN_PERMISSION_LEDGER_DECISION")
    steps.extend(str(value) for value in preferred.get("required_media_operations", []))
    steps.extend(
        [
            "GENERATE_EXACT_CLIP_TRANSCRIPT_GROUNDED_CAPTION_AND_ALIGNMENT",
            "EVALUATE_BATCH_TOPIC_STRUCTURE_AND_VISUAL_EVIDENCE",
            "BUILD_REVIEW_ONLY_ACTIVATION_CANDIDATE",
        ]
    )
    return {
        "account_id": "night_scout",
        "content_route": "approved_source_clip",
        "status": "REQUIRES_APPROVED_MEDIA_PREPARATION",
        "preferred_path": "PREPARE_EXISTING_NON_QUARANTINED_CLIP" if preferred else "ACQUIRE_NEW_APPROVED_CLIP_SOURCE",
        "source_options": options,
        "excluded_options": excluded,
        "ordered_steps": steps,
        "required_approvals": approvals + ["CAPTION_AND_QUALITY_EVIDENCE_GENERATION"],
        "code_gaps": ["REVIEW_ONLY_ROUTE_EVIDENCE_BUILDER_REQUIRED"],
        "unsafe_existing_entrypoints": [
            "run_media_production_pipeline.py apply may download cut upload or write",
            "run_media_production_pipeline.py post-saved-media path can post",
        ],
        "completion_contract": _base_completion_contract(),
    }


def _quality_plan(slot: Mapping[str, Any]) -> dict[str, Any]:
    account_id = _text(slot.get("account_id"))
    route = _text(slot.get("content_route"))
    semantic = slot.get("semantic_evidence", {}) if isinstance(slot.get("semantic_evidence"), Mapping) else {}
    public_present = bool(slot.get("public_post_text_present"))
    hash_status = _text(semantic.get("public_post_hash_status"))
    identity = _text(slot.get("source_post_id") or slot.get("clip_candidate_id"))
    if route == "direct_reference_media":
        first_step = "GENERATE_SOURCE_PRESERVING_CAPTION_FROM_EXACT_PARENT_POST"
        preferred = "REGENERATE_DIRECT_CAPTION_AND_COMPLETE_EVIDENCE"
    else:
        first_step = "REGENERATE_EXACT_CLIP_TRANSCRIPT_GROUNDED_CAPTION"
        preferred = "REGENERATE_CLIP_ALIGNMENT_AND_COMPLETE_EVIDENCE"
    steps: list[str] = []
    if hash_status == "MISMATCH":
        steps.append("DO_NOT_REUSE_MISMATCHED_PUBLIC_POST_ALIGNMENT")
    if not public_present or hash_status in {"MISMATCH", "MISSING", "NO_PUBLIC_TEXT"}:
        steps.append(first_step)
    steps.extend(
        [
            "RUN_EXACT_SEMANTIC_AND_MEDIA_VALIDATION",
            "RUN_PUBLIC_POST_PERSONA_AND_INTERNAL_LEAK_VALIDATION",
            "EVALUATE_BATCH_DIVERSITY_TOPIC_AND_STRUCTURE",
            "BUILD_VISUAL_PLAN_V1_EVIDENCE_FOR_EXACT_MEDIA",
            "VERIFY_PUBLIC_POST_HASH_MATCHES_ALIGNMENT",
            "BUILD_REVIEW_ONLY_ACTIVATION_CANDIDATE",
        ]
    )
    return {
        "account_id": account_id,
        "content_route": route,
        "status": "QUALITY_EVIDENCE_REGENERATION_REQUIRED",
        "identity": identity,
        "preferred_path": preferred,
        "source_options": [],
        "excluded_options": [],
        "ordered_steps": steps,
        "required_approvals": ["CAPTION_AND_QUALITY_EVIDENCE_GENERATION"],
        "code_gaps": [
            "REVIEW_ONLY_ROUTE_EVIDENCE_BUILDER_REQUIRED",
            "VISUAL_PLAN_V1_EVIDENCE_ENRICHER_REQUIRED",
        ],
        "unsafe_existing_entrypoints": [
            "Direct prepare path creates READY inventory" if route == "direct_reference_media" else "Media production apply path can mutate media and Sheets",
            "Existing mismatched or BLOCKED evidence must not be copied",
        ],
        "evidence_diagnostics": {
            "candidate_blockers": list(slot.get("candidate_blockers", [])),
            "semantic_match_type": _text(semantic.get("match_type")),
            "semantic_status": _text(semantic.get("status")),
            "public_post_hash_status": hash_status,
            "alignment_joinable": bool(semantic.get("joinable")),
        },
        "completion_contract": _base_completion_contract(),
    }


def _complete_plan(slot: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "account_id": _text(slot.get("account_id")),
        "content_route": _text(slot.get("content_route")),
        "status": "NO_REPAIR_REQUIRED",
        "preferred_path": "USE_CURRENT_VALIDATED_CANDIDATE",
        "source_options": [],
        "excluded_options": [],
        "ordered_steps": ["REVALIDATE_BEFORE_REVIEW_ONLY_CANDIDATE_BUILD"],
        "required_approvals": [],
        "code_gaps": [],
        "unsafe_existing_entrypoints": [],
        "completion_contract": _base_completion_contract(),
    }


def build_repair_plan(
    audit: Mapping[str, Any],
    *,
    source_posts: list[dict[str, Any]],
    source_post_media: list[dict[str, Any]],
    source_media_understanding: list[dict[str, Any]],
    media_permissions: list[dict[str, Any]],
    video_clip_candidates: list[dict[str, Any]],
    source_videos: list[dict[str, Any]],
    media_assets: list[dict[str, Any]],
    permission_checker: PermissionChecker | None = None,
) -> dict[str, Any]:
    audit_map = _audit_slots(audit)
    slots: list[dict[str, Any]] = []
    for account_id in ACCOUNTS:
        for route in ROUTES:
            audit_slot = audit_map.get((account_id, route), {
                "account_id": account_id,
                "content_route": route,
                "status": "SOURCE_MISSING",
                "selection_blocked_reasons": [],
            })
            if _text(audit_slot.get("status")) == "QUALITY_COMPLETE":
                plan = _complete_plan(audit_slot)
            elif account_id == "night_scout" and route == "direct_reference_media" and _text(audit_slot.get("status")) == "SOURCE_MISSING":
                plan = _night_direct_plan(
                    audit_slot,
                    source_posts=source_posts,
                    source_post_media=source_post_media,
                    source_media_understanding=source_media_understanding,
                    permissions=media_permissions,
                    permission_checker=permission_checker,
                )
            elif account_id == "night_scout" and route == "approved_source_clip" and _text(audit_slot.get("status")) == "SOURCE_MISSING":
                plan = _night_clip_plan(
                    audit_slot,
                    video_clip_candidates=video_clip_candidates,
                    source_videos=source_videos,
                    media_assets=media_assets,
                    permissions=media_permissions,
                    permission_checker=permission_checker,
                )
            else:
                plan = _quality_plan(audit_slot)
            plan["audit_status"] = _text(audit_slot.get("status"))
            slots.append(plan)

    required_approval_slots = sum(1 for slot in slots if slot.get("required_approvals"))
    code_gap_slots = sum(1 for slot in slots if slot.get("code_gaps"))
    external_operations = sorted({
        approval
        for slot in slots
        for approval in slot.get("required_approvals", [])
        if approval in {"EXTERNAL_VIDEO_DOWNLOAD", "LOCAL_CLIP_CUT", "CLOUD_MEDIA_UPLOAD"}
    })
    complete = sum(1 for slot in slots if slot["status"] == "NO_REPAIR_REQUIRED")
    return {
        "status": "READ_ONLY_COMPLETE",
        "repair_status": "READY_FOR_REVIEW" if complete == len(slots) else "BLOCKED_REQUIRES_APPROVAL_AND_IMPLEMENTATION",
        "slot_count": len(slots),
        "repair_required_count": len(slots) - complete,
        "approval_required_slot_count": required_approval_slots,
        "code_gap_slot_count": code_gap_slots,
        "planned_external_operations": external_operations,
        "slots": slots,
        "safety": {
            "production_write": False,
            "permission_mutation": False,
            "caption_generation": False,
            "evidence_write": False,
            "media_download": False,
            "media_cut": False,
            "media_upload": False,
            "queue_write": False,
            "ready_transition": False,
            "workflow_dispatch": False,
            "sns_post": False,
        },
    }


def _read_records(client: Any, logical: str) -> list[dict[str, Any]]:
    from sheets_client import TAB_DEFINITIONS
    from sheets_record_reader import read_records_safely

    client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    return [dict(row) for row in read_records_safely(client, logical)]


def load_production_repair_plan() -> dict[str, Any]:
    from audit_media_activation_quality_evidence import load_production_audit
    from config_loader import get_config
    from final_production_contracts import is_active_permission
    from sheets_client import SheetsClient

    audit = load_production_audit()
    config = get_config()
    client = SheetsClient(config["sheet_id"], config["sa_dict"], dry_run=True)
    datasets = {
        logical: _read_records(client, logical)
        for logical in (
            "source_posts",
            "source_post_media",
            "source_media_understanding",
            "media_permissions",
            "video_clip_candidates",
            "source_videos",
            "media_assets",
        )
    }
    return build_repair_plan(
        audit,
        source_posts=datasets["source_posts"],
        source_post_media=datasets["source_post_media"],
        source_media_understanding=datasets["source_media_understanding"],
        media_permissions=datasets["media_permissions"],
        video_clip_candidates=datasets["video_clip_candidates"],
        source_videos=datasets["source_videos"],
        media_assets=datasets["media_assets"],
        permission_checker=is_active_permission,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    unsafe = safety_blockers()
    if unsafe:
        print(json.dumps({"status": "BLOCKED_UNSAFE_ENV", "blocked_reasons": unsafe}))
        return 1
    if not args.use_sheets:
        print(json.dumps({"status": "BLOCKED", "blocked_reasons": ["--use-sheets is required"]}))
        return 1

    report = load_production_repair_plan()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("=== MEDIA ACTIVATION REPAIR PLAN ===")
    print(f"READ_STATUS={report['status']}")
    print(f"REPAIR_STATUS={report['repair_status']}")
    print(f"SLOT_COUNT={report['slot_count']}")
    print(f"REPAIR_REQUIRED_COUNT={report['repair_required_count']}")
    print(f"APPROVAL_REQUIRED_SLOT_COUNT={report['approval_required_slot_count']}")
    print(f"CODE_GAP_SLOT_COUNT={report['code_gap_slot_count']}")
    print("PLANNED_EXTERNAL_OPERATIONS=" + ",".join(report["planned_external_operations"]))
    for slot in report["slots"]:
        approvals = ",".join(slot.get("required_approvals", [])) or "NONE"
        gaps = ",".join(slot.get("code_gaps", [])) or "NONE"
        print(
            "SLOT:"
            f"{slot['account_id']}:"
            f"{slot['content_route']}:"
            f"status={slot['status']}:"
            f"preferred={slot['preferred_path']}:"
            f"approvals={approvals}:"
            f"code_gaps={gaps}"
        )
        for option in slot.get("source_options", []):
            identity = option.get("source_post_id") or option.get("clip_candidate_id") or option.get("media_asset_id") or ""
            operations = ",".join(option.get("required_media_operations", [])) or "NONE"
            permission = option.get("permission_review", {})
            print(
                "OPTION:"
                f"{slot['account_id']}:"
                f"{slot['content_route']}:"
                f"identity={identity}:"
                f"status={option.get('status', '')}:"
                f"preferred={str(bool(option.get('preferred'))).lower()}:"
                f"active_permission={str(bool(permission.get('active_permission_present'))).lower()}:"
                f"media_operations={operations}"
            )
        for excluded in slot.get("excluded_options", []):
            identity = excluded.get("clip_candidate_id") or excluded.get("media_asset_id") or ""
            print(
                "EXCLUDED:"
                f"{slot['account_id']}:"
                f"{slot['content_route']}:"
                f"identity={identity}:"
                f"status={excluded.get('status', '')}:"
                f"reason={excluded.get('reason', '')}"
            )
        print("STEPS:" + slot["account_id"] + ":" + slot["content_route"] + ":" + "|".join(slot.get("ordered_steps", [])))
    print(f"REPORT={args.output}")
    print("PASS: read-only repair planning")
    print("PASS: no permission grant, generation, write, media operation, queue transition, workflow dispatch or post")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
