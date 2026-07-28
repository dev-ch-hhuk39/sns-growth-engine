#!/usr/bin/env python3
"""Build and verify human-approved source identity repair plans.

This module deliberately has no Sheets client and no write operation.  It is
used to turn a read-only snapshot into a reviewable plan, then to verify a
separately approved repair snapshot without inferring that a write occurred.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from plan_wp3c_production_repairs import generate_hash, plan_parent_repair


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _rows_hash(rows: list[dict[str, Any]]) -> str:
    normalized = sorted((_canonical_json(row) for row in rows))
    return hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()


def _parent_snapshot_hash(parent_id: str, datasets: dict[str, list[dict[str, Any]]]) -> str:
    parents = [row for row in datasets.get("source_posts", []) if str(row.get("source_post_id", "")) == parent_id]
    children = [row for row in datasets.get("source_post_media", []) if str(row.get("source_post_id", "")) == parent_id]
    return generate_hash({"parent_id": parent_id, "parents": _rows_hash(parents), "children": _rows_hash(children)})


def _parent_ids(datasets: dict[str, list[dict[str, Any]]]) -> list[str]:
    ids = {
        str(row.get("source_post_id", "")).strip()
        for table in ("source_posts", "source_post_media")
        for row in datasets.get(table, [])
        if str(row.get("source_post_id", "")).strip()
    }
    return sorted(ids)


def build_identity_repair_plan(
    datasets: dict[str, list[dict[str, Any]]],
    *,
    implementation_head: str,
    origin_main: str,
    planned_at: str | None = None,
) -> dict[str, Any]:
    """Discover all source-parent defects; produce no mutation instruction."""
    planned_at = planned_at or datetime.now(timezone.utc).isoformat()
    posts_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    children_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in datasets.get("source_posts", []):
        posts_by_id[str(row.get("source_post_id", ""))].append(row)
    for row in datasets.get("source_post_media", []):
        children_by_id[str(row.get("source_post_id", ""))].append(row)

    repairs: list[dict[str, Any]] = []
    audit_records: list[dict[str, Any]] = []
    for parent_id in _parent_ids(datasets):
        repair = plan_parent_repair(parent_id, posts_by_id[parent_id], children_by_id[parent_id])
        if not repair["operations"] and not repair["blocker_codes"]:
            continue
        repair["before_snapshot_hash"] = _parent_snapshot_hash(parent_id, datasets)
        repairs.append(repair)
        audit_records.append({
            "repair_plan_id": "",
            "affected_row_type": "source_post",
            "affected_row_id": parent_id,
            "old_hash": repair["before_snapshot_hash"],
            "new_hash": "",
            "reason": ",".join(repair["blocker_codes"]) or ",".join(op["operation"] for op in repair["operations"]),
            "applied_at": "",
            "verifier_result": "PENDING_HUMAN_APPROVAL",
        })

    plan_seed = {
        "implementation_head": implementation_head,
        "origin_main": origin_main,
        "affected_parent_ids": [repair["source_post_id"] for repair in repairs],
        "snapshot_hash": _rows_hash(datasets.get("source_posts", []) + datasets.get("source_post_media", [])),
    }
    repair_plan_id = f"source_identity_{generate_hash(plan_seed)[:16]}"
    for record in audit_records:
        record["repair_plan_id"] = repair_plan_id
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_IDENTITY_REPAIR_PLAN",
        "repair_plan_id": repair_plan_id,
        "implementation_head": implementation_head,
        "origin_main": origin_main,
        "planned_at": planned_at,
        "apply_allowed": False,
        "approval_requirement": "HUMAN_APPROVAL_REQUIRED",
        "affected_row_count": len(repairs),
        "parent_repairs": repairs,
        "audit_records": audit_records,
    }


def verify_identity_repair_outcome(
    before_plan: dict[str, Any], after_datasets: dict[str, list[dict[str, Any]]], *, verified_at: str | None = None
) -> dict[str, Any]:
    """Compare an approved post-repair snapshot without applying anything."""
    verified_at = verified_at or datetime.now(timezone.utc).isoformat()
    after_plan = build_identity_repair_plan(
        after_datasets,
        implementation_head=str(before_plan.get("implementation_head", "")),
        origin_main=str(before_plan.get("origin_main", "")),
        planned_at=verified_at,
    )
    remaining = {item["source_post_id"] for item in after_plan["parent_repairs"]}
    records: list[dict[str, Any]] = []
    for before in before_plan.get("parent_repairs", []):
        parent_id = str(before.get("source_post_id", ""))
        success = parent_id not in remaining
        records.append({
            "repair_plan_id": str(before_plan.get("repair_plan_id", "")),
            "affected_row_type": "source_post",
            "affected_row_id": parent_id,
            "old_hash": str(before.get("before_snapshot_hash", "")),
            "new_hash": _parent_snapshot_hash(parent_id, after_datasets),
            "reason": "SOURCE_IDENTITY_REPAIR",
            "applied_at": "" if not success else verified_at,
            "verifier_result": "PASS" if success else "FAIL_REMAINING_IDENTITY_DEFECT",
        })
    return {
        "schema_version": 1,
        "mode": "READ_ONLY_IDENTITY_REPAIR_VERIFIER",
        "repair_plan_id": str(before_plan.get("repair_plan_id", "")),
        "verified_at": verified_at,
        "status": "PASS" if records and all(row["verifier_result"] == "PASS" for row in records) else "FAIL",
        "affected_row_count": len(records),
        "audit_records": records,
        "remaining_parent_repairs": after_plan["parent_repairs"],
    }
