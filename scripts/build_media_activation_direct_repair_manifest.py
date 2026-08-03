#!/usr/bin/env python3
"""Build deterministic, non-executable repair manifests for Direct media slots.

The builder consumes the read-only media activation source suitability inventory
and emits exactly one declarative manifest for each Direct route.  It never
grants permission, downloads, uploads, probes, or analyzes media, writes Sheets,
creates queue rows, promotes READY, dispatches workflows, or posts to an SNS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

ACCOUNTS = ("night_scout", "liver_manager")
ROUTE = "direct_reference_media"
SCHEMA_VERSION = "media_activation_direct_repair_manifest_v1"

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

DIRECT_PERMISSION_FLAGS = (
    "allow_cloudinary_storage",
    "allow_original_repost",
    "allow_new_caption",
)

FORBIDDEN_CANDIDATE_STATES = {
    "EXCLUDED",
    "SOURCE_EVIDENCE_UNSUITABLE",
}

FORBIDDEN_BLOCKER_MARKERS = (
    "synthetic",
    "already_used",
    "reuse_status_posted",
    "quarantined",
    "unsupported_media_type",
    "video_duration_above_direct_limit",
    "individual_source_post_url_required",
)

REPAIR_KIND_BY_SUFFIX = {
    "media_not_uploaded": "PERSISTED_MEDIA_UPLOAD_EVIDENCE_REPAIR",
    "persisted_asset_link_missing": "PERSISTED_ASSET_LINK_REPAIR",
    "media_understanding_empty": "MEDIA_UNDERSTANDING_CONTENT_REPAIR",
    "media_understanding_not_pass": "MEDIA_UNDERSTANDING_STATUS_REPAIR",
    "direct_media_evidence_missing": "DIRECT_MEDIA_EVIDENCE_REPAIR",
    "source_post_media_missing": "SOURCE_POST_MEDIA_JOIN_REPAIR",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _true(value: Any) -> bool:
    return value is True or _text(value).lower() in {"1", "true", "yes", "pass"}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def safety_blockers(environ: Mapping[str, str] | None = None) -> list[str]:
    source = os.environ if environ is None else environ
    return [f"{name}=true" for name in DANGEROUS_ENV if _true(source.get(name))]


def _identity(row: Mapping[str, Any]) -> str:
    return _text(row.get("source_post_id") or row.get("clip_candidate_id"))


def _validate_direct_inventory_contract(inventory: Mapping[str, Any]) -> None:
    raw_slots = inventory.get("slots")
    if not isinstance(raw_slots, Sequence) or isinstance(raw_slots, (str, bytes)):
        raise ValueError("inventory_slots_invalid")

    direct_slot_counts = {account_id: 0 for account_id in ACCOUNTS}
    for item in raw_slots:
        if not isinstance(item, Mapping):
            raise ValueError("inventory_slot_not_mapping")
        account_id = _text(item.get("account_id"))
        content_route = _text(item.get("content_route"))
        if content_route != ROUTE:
            continue
        if account_id not in ACCOUNTS:
            raise ValueError(f"inventory_unexpected_direct_account:{account_id or 'EMPTY'}")
        direct_slot_counts[account_id] += 1

    missing = sorted(
        account_id
        for account_id, count in direct_slot_counts.items()
        if count == 0
    )
    duplicates = sorted(
        account_id
        for account_id, count in direct_slot_counts.items()
        if count > 1
    )
    if missing:
        raise ValueError("inventory_direct_slots_missing:" + ",".join(missing))
    if duplicates:
        raise ValueError("inventory_direct_slots_duplicated:" + ",".join(duplicates))

    candidates = inventory.get("candidates")
    if not isinstance(candidates, Mapping):
        raise ValueError("inventory_candidates_invalid")
    for account_id in ACCOUNTS:
        account_rows = candidates.get(account_id)
        if not isinstance(account_rows, Mapping):
            raise ValueError(f"inventory_candidate_account_missing:{account_id}")
        rows = account_rows.get(ROUTE)
        if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
            raise ValueError(f"inventory_direct_candidates_invalid:{account_id}")
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError(f"inventory_direct_candidate_not_mapping:{account_id}")
            row_account = _text(row.get("account_id"))
            row_route = _text(row.get("content_route"))
            if row_account != account_id:
                raise ValueError(
                    f"inventory_direct_candidate_account_mismatch:{account_id}:{row_account or 'EMPTY'}"
                )
            if row_route != ROUTE:
                raise ValueError(
                    f"inventory_direct_candidate_route_mismatch:{account_id}:{row_route or 'EMPTY'}"
                )


def _slot_index(inventory: Mapping[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (_text(item.get("account_id")), _text(item.get("content_route"))): dict(item)
        for item in inventory.get("slots", [])
        if isinstance(item, Mapping)
    }


def _candidate_rows(inventory: Mapping[str, Any], account_id: str) -> list[dict[str, Any]]:
    candidates = inventory.get("candidates", {})
    if not isinstance(candidates, Mapping):
        return []
    account = candidates.get(account_id, {})
    if not isinstance(account, Mapping):
        return []
    rows = account.get(ROUTE, [])
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes)):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _candidate_is_forbidden(row: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    state = _text(row.get("candidate_status"))
    if state in FORBIDDEN_CANDIDATE_STATES:
        reasons.append(f"candidate_status:{state}")

    hard_blockers = [_text(value) for value in row.get("hard_blockers", []) if _text(value)]
    if hard_blockers:
        reasons.extend(f"hard_blocker:{value}" for value in hard_blockers)

    all_blockers = {
        _text(value)
        for field in ("blockers", "repair_blockers", "hard_blockers")
        for value in row.get(field, [])
        if _text(value)
    }
    for blocker in sorted(all_blockers):
        lowered = blocker.lower()
        if any(marker in lowered for marker in FORBIDDEN_BLOCKER_MARKERS):
            reasons.append(f"forbidden_blocker:{blocker}")

    if row.get("external_operations"):
        reasons.append("candidate_external_operations_present")

    return bool(reasons), sorted(set(reasons))


def _select_candidate(
    slot: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    recommended_id = _text(slot.get("recommended_candidate_id"))
    ordered = [dict(row) for row in rows]
    ordered.sort(
        key=lambda row: (
            0 if _identity(row) == recommended_id and recommended_id else 1,
            -_number(row.get("candidate_score")),
            _identity(row),
        )
    )

    rejected: list[dict[str, Any]] = []
    for row in ordered:
        forbidden, reasons = _candidate_is_forbidden(row)
        if forbidden:
            rejected.append(
                {
                    "candidate_id": _identity(row),
                    "candidate_status": _text(row.get("candidate_status")),
                    "reasons": reasons,
                }
            )
            continue
        if _text(row.get("candidate_status")) not in {
            "SOURCE_REPAIR_REQUIRED",
            "PERMISSION_REVIEW_REQUIRED",
            "READY_FOR_REVIEW_EVIDENCE",
        }:
            rejected.append(
                {
                    "candidate_id": _identity(row),
                    "candidate_status": _text(row.get("candidate_status")),
                    "reasons": ["candidate_not_repair_manifest_eligible"],
                }
            )
            continue
        return row, rejected
    return {}, rejected


def _permission_gate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    permission_active = candidate.get("permission_active") is True
    source_blockers = sorted(
        {
            _text(value)
            for value in candidate.get("permission_scope_missing", [])
            if _text(value)
        }
    )
    missing_or_unverified_flags = (
        source_blockers
        if permission_active
        else list(DIRECT_PERMISSION_FLAGS)
    )
    ready = permission_active and not source_blockers
    return {
        "status": "PASS_ACTIVE_PERMISSION" if ready else "BLOCKED_HUMAN_DECISION_REQUIRED",
        "permission_id": _text(candidate.get("permission_id")),
        "active_permission_present": permission_active,
        "source_permission_blockers": source_blockers,
        "missing_or_unverified_flags": missing_or_unverified_flags,
        "decision_policy": "HUMAN_DECISION_ONLY_NO_AUTOMATIC_GRANT",
        "media_repair_may_begin": ready,
    }


def _split_reason(reason: str) -> tuple[str, str]:
    value = _text(reason)
    if ":" not in value:
        return "", value
    target, suffix = value.rsplit(":", 1)
    return target, suffix


def _repair_steps(candidate: Mapping[str, Any], *, permission_ready: bool) -> list[dict[str, Any]]:
    reasons = sorted(
        {
            _text(value)
            for value in candidate.get("repair_blockers", candidate.get("blockers", []))
            if _text(value)
        }
    )
    steps: list[dict[str, Any]] = []
    for index, reason in enumerate(reasons, start=1):
        target, suffix = _split_reason(reason)
        kind = REPAIR_KIND_BY_SUFFIX.get(suffix, "SOURCE_EVIDENCE_REPAIR_REVIEW")
        step = {
            "step_id": f"repair-{index:02d}",
            "kind": kind,
            "target_id": target,
            "source_blocker": reason,
            "status": "REVIEWABLE_AFTER_PERMISSION" if permission_ready else "BLOCKED_BY_PERMISSION_GATE",
            "requires_human_approval": True,
            "execution_allowed": False,
            "executable_command": "",
            "completion_evidence": _completion_evidence(kind),
        }
        steps.append(step)
    return steps


def _completion_evidence(kind: str) -> list[str]:
    if kind == "PERSISTED_MEDIA_UPLOAD_EVIDENCE_REPAIR":
        return ["upload_status=UPLOADED", "storage_url_present=true"]
    if kind == "PERSISTED_ASSET_LINK_REPAIR":
        return ["source_post_media_to_media_asset_join_present=true"]
    if kind in {
        "MEDIA_UNDERSTANDING_CONTENT_REPAIR",
        "MEDIA_UNDERSTANDING_STATUS_REPAIR",
    }:
        return ["source_media_understanding.status=PASS", "grounded_media_evidence_present=true"]
    if kind == "DIRECT_MEDIA_EVIDENCE_REPAIR":
        return ["direct_media_evidence_present=true"]
    if kind == "SOURCE_POST_MEDIA_JOIN_REPAIR":
        return ["source_post_media_row_present=true"]
    return ["inventory_blocker_removed=true"]


def _manifest_status(candidate: Mapping[str, Any], gate: Mapping[str, Any], steps: Sequence[Mapping[str, Any]]) -> str:
    if not candidate:
        return "NEW_ELIGIBLE_DIRECT_SOURCE_REQUIRED"
    if gate.get("status") != "PASS_ACTIVE_PERMISSION":
        return "HUMAN_PERMISSION_REVIEW_REQUIRED_BEFORE_REPAIR"
    if steps:
        return "EVIDENCE_REPAIR_SPEC_READY_FOR_HUMAN_REVIEW"
    return "NO_REPAIR_REQUIRED_RUN_REVIEW_EVIDENCE_BUILDER"


def _next_stage(
    candidate: Mapping[str, Any],
    gate: Mapping[str, Any],
    steps: Sequence[Mapping[str, Any]],
) -> str:
    if not candidate:
        return "ACQUIRE_NEW_ELIGIBLE_DIRECT_SOURCE"
    if gate.get("status") != "PASS_ACTIVE_PERMISSION":
        return "HUMAN_PERMISSION_REVIEW"
    if steps:
        return "HUMAN_REPAIR_SPEC_REVIEW"
    return "RUN_REVIEW_EVIDENCE_BUILDER_READ_ONLY"


def _build_slot_manifest(
    account_id: str,
    slot: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    candidate, rejected = _select_candidate(slot, candidates)
    gate = _permission_gate(candidate) if candidate else {
        "status": "NOT_APPLICABLE_NO_ELIGIBLE_SOURCE",
        "permission_id": "",
        "active_permission_present": False,
        "source_permission_blockers": [],
        "missing_or_unverified_flags": [],
        "decision_policy": "HUMAN_DECISION_ONLY_NO_AUTOMATIC_GRANT",
        "media_repair_may_begin": False,
    }
    steps = _repair_steps(
        candidate,
        permission_ready=bool(gate.get("media_repair_may_begin")),
    ) if candidate else []

    core = {
        "schema_version": SCHEMA_VERSION,
        "account_id": account_id,
        "content_route": ROUTE,
        "manifest_status": _manifest_status(candidate, gate, steps),
        "source_inventory_route_status": _text(slot.get("route_status")),
        "selected_candidate": {
            "source_post_id": _text(candidate.get("source_post_id")),
            "source_id": _text(candidate.get("source_id")),
            "source_url": _text(candidate.get("source_url")),
            "platform": _text(candidate.get("platform")),
            "candidate_status": _text(candidate.get("candidate_status")),
            "candidate_score": candidate.get("candidate_score", ""),
            "source_text_hash": _text(candidate.get("source_text", {}).get("hash"))
            if isinstance(candidate.get("source_text"), Mapping)
            else "",
        },
        "permission_gate": gate,
        "repair_steps": steps,
        "rejected_candidates": rejected,
        "review_handoff": {
            "next_stage": _next_stage(candidate, gate, steps),
            "automatic_execution": False,
            "queue_creation_allowed": False,
            "ready_transition_allowed": False,
        },
        "executable_commands": [],
        "external_operations": [],
    }
    core["manifest_hash"] = _sha(core)
    return core


def _validate_inventory_safety(inventory: Mapping[str, Any]) -> None:
    if inventory.get("planned_external_operations"):
        raise ValueError("inventory_planned_external_operations_present")
    safety = inventory.get("safety", {})
    if not isinstance(safety, Mapping):
        raise ValueError("inventory_safety_missing")
    unsafe = sorted(_text(key) for key, value in safety.items() if value is not False)
    if unsafe:
        raise ValueError("inventory_safety_not_false:" + ",".join(unsafe))
    if _text(inventory.get("read_status")) != "READ_ONLY_COMPLETE":
        raise ValueError("inventory_not_read_only_complete")


def build_direct_repair_manifest(inventory: Mapping[str, Any]) -> dict[str, Any]:
    _validate_inventory_safety(inventory)
    _validate_direct_inventory_contract(inventory)
    slots = _slot_index(inventory)
    manifests: list[dict[str, Any]] = []
    for account_id in ACCOUNTS:
        slot = slots.get((account_id, ROUTE), {})
        manifests.append(
            _build_slot_manifest(
                account_id,
                slot,
                _candidate_rows(inventory, account_id),
            )
        )

    permission_blocked = [
        row["account_id"]
        for row in manifests
        if row["manifest_status"] == "HUMAN_PERMISSION_REVIEW_REQUIRED_BEFORE_REPAIR"
    ]
    source_required = [
        row["account_id"]
        for row in manifests
        if row["manifest_status"] == "NEW_ELIGIBLE_DIRECT_SOURCE_REQUIRED"
    ]
    repair_review = [
        row["account_id"]
        for row in manifests
        if row["manifest_status"] == "EVIDENCE_REPAIR_SPEC_READY_FOR_HUMAN_REVIEW"
    ]
    review_evidence_ready = [
        row["account_id"]
        for row in manifests
        if row["manifest_status"] == "NO_REPAIR_REQUIRED_RUN_REVIEW_EVIDENCE_BUILDER"
    ]

    status = (
        "BLOCKED_NEW_DIRECT_SOURCE_REQUIRED"
        if source_required
        else "BLOCKED_HUMAN_PERMISSION_REVIEW_REQUIRED"
        if permission_blocked
        else "REPAIR_MANIFEST_READY_FOR_HUMAN_REVIEW"
        if repair_review
        else "DIRECT_SOURCES_READY_FOR_REVIEW_EVIDENCE"
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "manifest_route": ROUTE,
        "status": status,
        "read_status": "READ_ONLY_COMPLETE",
        "manifest_count": len(manifests),
        "permission_blocked_accounts": permission_blocked,
        "new_source_required_accounts": source_required,
        "repair_review_accounts": repair_review,
        "review_evidence_ready_accounts": review_evidence_ready,
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
    report["report_hash"] = _sha(report)
    return report


def load_production_manifest() -> dict[str, Any]:
    from inventory_media_activation_sources import load_production_inventory

    return build_direct_repair_manifest(load_production_inventory())


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

    report = load_production_manifest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=== MEDIA ACTIVATION DIRECT REPAIR MANIFEST ===")
    print(f"READ_STATUS={report['read_status']}")
    print(f"MANIFEST_ROUTE={report['manifest_route']}")
    print(f"MANIFEST_STATUS={report['status']}")
    print(f"MANIFEST_COUNT={report['manifest_count']}")
    for manifest in report["manifests"]:
        selected = manifest["selected_candidate"]
        gate = manifest["permission_gate"]
        print(
            "MANIFEST:"
            f"{manifest['account_id']}:"
            f"status={manifest['manifest_status']}:"
            f"candidate={selected['source_post_id'] or 'NONE'}:"
            f"permission_gate={gate['status']}:"
            f"repair_step_count={len(manifest['repair_steps'])}:"
            f"hash={manifest['manifest_hash']}"
        )
        for step in manifest["repair_steps"]:
            print(
                "REPAIR_STEP:"
                f"{manifest['account_id']}:"
                f"{step['step_id']}:"
                f"kind={step['kind']}:"
                f"target={step['target_id'] or 'SOURCE'}:"
                f"status={step['status']}"
            )
    print(f"PERMISSION_BLOCKED_ACCOUNTS={','.join(report['permission_blocked_accounts'])}")
    print(f"NEW_DIRECT_SOURCE_REQUIRED_ACCOUNTS={','.join(report['new_source_required_accounts'])}")
    print(f"REPAIR_REVIEW_ACCOUNTS={','.join(report['repair_review_accounts'])}")
    print(f"REVIEW_EVIDENCE_READY_ACCOUNTS={','.join(report['review_evidence_ready_accounts'])}")
    print(f"PLANNED_EXTERNAL_OPERATIONS={','.join(report['planned_external_operations'])}")
    print(f"EXECUTABLE_COMMANDS={','.join(report['executable_commands'])}")
    print(f"REPORT={args.output}")
    print("PASS: Production and Sheets read-only manifest")
    print("PASS: no permission grant, media operation, queue write, READY transition, dispatch or post")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
