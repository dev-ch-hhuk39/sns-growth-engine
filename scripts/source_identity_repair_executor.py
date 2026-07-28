#!/usr/bin/env python3
"""Gated executor for a human-approved source identity repair plan.

The pure functions are intentionally separated from the Sheets adapter.  No
caller can apply a repair without a reviewed plan, matching precondition hash,
and explicit production gate.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from source_identity_repair_contract import _parent_snapshot_hash, row_fingerprint, verify_identity_repair_outcome


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_preconditions(plan: dict[str, Any], datasets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    mismatches: list[str] = []
    for repair in plan.get("parent_repairs", []):
        parent_id = str(repair.get("source_post_id", ""))
        expected = str(repair.get("before_snapshot_hash", ""))
        actual = _parent_snapshot_hash(parent_id, datasets)
        if not parent_id or not expected or expected != actual:
            mismatches.append(parent_id or "MISSING_PARENT_ID")
    return {"status": "PASS" if not mismatches else "BLOCKED", "mismatched_parent_ids": mismatches}


def _find(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any] | None:
    matches = [row for row in rows if str(row.get(key, "")) == value]
    return matches[0] if len(matches) == 1 else None


def _find_by_fingerprint(rows: list[dict[str, Any]], fingerprint: str) -> tuple[int, dict[str, Any]] | None:
    matches = [(index, row) for index, row in enumerate(rows) if row_fingerprint(row) == fingerprint]
    return matches[0] if len(matches) == 1 else None


def apply_plan_in_memory(plan: dict[str, Any], datasets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Apply only plan operations to a snapshot, returning audit and rollback data.

    This has no external I/O and is used by the Sheets adapter only after its
    own read-only precondition check.
    """
    preconditions = validate_preconditions(plan, datasets)
    if preconditions["status"] != "PASS":
        return {"status": "BLOCKED_PRECONDITION", "preconditions": preconditions, "datasets": datasets, "audit_records": [], "rollback_plan": []}

    working = deepcopy(datasets)
    audits: list[dict[str, Any]] = []
    rollback: list[dict[str, Any]] = []
    try:
        for repair in plan.get("parent_repairs", []):
            if not repair.get("apply_eligible"):
                raise RuntimeError("PLAN_CONTAINS_NON_ELIGIBLE_REPAIR")
            parent_id = str(repair["source_post_id"])
            operation_kinds = {str(operation.get("operation", "")) for operation in repair.get("operations", [])}
            parent = _find(working.get("source_posts", []), "source_post_id", parent_id)
            if parent is None and operation_kinds & {"SET_PARENT_MEDIA_COUNT", "SET_CHILD_CANONICAL_URL_FROM_PARENT"}:
                raise RuntimeError("PARENT_NOT_UNIQUELY_RESOLVABLE")
            for operation in repair.get("operations", []):
                kind = str(operation.get("operation", ""))
                if kind == "SET_PARENT_MEDIA_COUNT":
                    row, field, target = parent, "media_count", operation.get("to")
                    row_type, row_id = "source_post", parent_id
                elif kind in {"SET_CHILD_CANONICAL_URL_FROM_PARENT", "SET_MEDIA_INDEX"}:
                    row_id = str(operation.get("source_post_media_id", ""))
                    row = _find(working.get("source_post_media", []), "source_post_media_id", row_id)
                    if row is None:
                        raise RuntimeError("CHILD_NOT_UNIQUELY_RESOLVABLE")
                    field = "canonical_post_url" if kind == "SET_CHILD_CANONICAL_URL_FROM_PARENT" else "media_index"
                    target = parent.get("canonical_post_url", "") if kind == "SET_CHILD_CANONICAL_URL_FROM_PARENT" else operation.get("to")
                    row_type = "source_post_media"
                elif kind == "SET_CHILD_CANONICAL_URL_BY_FINGERPRINT":
                    match = _find_by_fingerprint(working.get("source_post_media", []), str(operation.get("row_fingerprint", "")))
                    if match is None:
                        raise RuntimeError("CHILD_FINGERPRINT_NOT_UNIQUELY_RESOLVABLE")
                    _, row = match
                    row_id = str(operation.get("source_post_media_id", ""))
                    field, target, row_type = "canonical_post_url", operation.get("to"), "source_post_media"
                elif kind in {"DELETE_SOURCE_POST_ROW", "DELETE_SOURCE_POST_MEDIA_ROW"}:
                    table = "source_posts" if kind == "DELETE_SOURCE_POST_ROW" else "source_post_media"
                    match = _find_by_fingerprint(working.get(table, []), str(operation.get("row_fingerprint", "")))
                    if match is None:
                        raise RuntimeError("ROW_FINGERPRINT_NOT_UNIQUELY_RESOLVABLE")
                    index, row = match
                    row_id = str(row.get("source_post_id" if table == "source_posts" else "source_post_media_id", ""))
                    row_type, field, target = ("source_post" if table == "source_posts" else "source_post_media"), "__row__", "DELETED"
                    old = row_fingerprint(row)
                    deleted_snapshot = deepcopy(row)
                    del working[table][index]
                    audits.append({"repair_plan_id": plan.get("repair_plan_id", ""), "affected_row_type": row_type, "affected_row_id": row_id, "field": field, "old_value": old, "new_value": target, "reason": operation.get("reason", kind), "operation": kind, "row_fingerprint": operation.get("row_fingerprint", ""), "applied_at": _now(), "verifier_result": "PENDING"})
                    rollback.append({"affected_row_type": row_type, "affected_row_id": row_id, "field": field, "restore_row": deleted_snapshot, "row_fingerprint": operation.get("row_fingerprint", ""), "reason": f"ROLLBACK_{kind}"})
                    continue
                else:
                    raise RuntimeError("UNSUPPORTED_REPAIR_OPERATION")
                target_fingerprint = str(operation.get("row_fingerprint", "")) or row_fingerprint(row)
                old = row.get(field, "")
                row[field] = target
                audits.append({"repair_plan_id": plan.get("repair_plan_id", ""), "affected_row_type": row_type, "affected_row_id": row_id, "field": field, "old_value": old, "new_value": target, "reason": operation.get("reason", kind), "operation": kind, "row_fingerprint": target_fingerprint, "applied_at": _now(), "verifier_result": "PENDING"})
                rollback.append({"affected_row_type": row_type, "affected_row_id": row_id, "field": field, "restore_value": old, "row_fingerprint": target_fingerprint, "reason": f"ROLLBACK_{kind}"})
    except Exception as exc:
        return {"status": "PARTIAL_FAILED", "reason": type(exc).__name__, "error": str(exc), "datasets": working, "audit_records": audits, "rollback_plan": list(reversed(rollback))}

    verification = verify_identity_repair_outcome(plan, working)
    for record in audits:
        record["verifier_result"] = verification["status"]
    return {"status": "APPLIED" if verification["status"] == "PASS" else "PARTIAL_FAILED", "datasets": working, "audit_records": audits, "rollback_plan": list(reversed(rollback)), "verification": verification}


def production_apply_allowed(*, apply: bool, confirm: bool) -> bool:
    import os
    return apply and confirm and str(os.environ.get("ALLOW_SHEETS_IDENTITY_REPAIR", "")).lower() in {"1", "true", "yes"}
