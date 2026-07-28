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
from urllib.parse import parse_qs, urlsplit

from plan_wp3c_production_repairs import canonicalize_source_url, generate_hash, plan_parent_repair


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _rows_hash(rows: list[dict[str, Any]]) -> str:
    normalized = sorted((_canonical_json(row) for row in rows))
    return hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()


def row_fingerprint(row: dict[str, Any]) -> str:
    """Stable precondition for one Sheets row, independent of its row number."""
    return hashlib.sha256(_canonical_json(row).encode("utf-8")).hexdigest()


def _youtube_url_class(value: str) -> str:
    """Return individual, landing, or other without guessing a video identity."""
    parsed = urlsplit(str(value).strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    if host not in {"youtube.com", "m.youtube.com", "youtu.be"}:
        return "other"
    if host == "youtu.be" and path.strip("/"):
        return "individual"
    if path == "/watch" and parse_qs(parsed.query).get("v"):
        return "individual"
    if path.startswith("/shorts/") and len(path.split("/")) >= 3:
        return "individual"
    if path == "/watch" or path.startswith("/channel/") or path.startswith("/@") or path.startswith("/playlist"):
        return "landing"
    return "other"


def _canonical_individual_youtube_url(value: str) -> str:
    parsed = urlsplit(str(value).strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    if host == "youtu.be":
        return f"https://youtu.be{path}"
    if path == "/watch":
        video_id = parse_qs(parsed.query).get("v", [""])[0]
        return f"https://youtube.com/watch?v={video_id}" if video_id else ""
    if path.startswith("/shorts/"):
        return f"https://youtube.com{path}"
    return ""


def _safe_duplicate_parent_repair(
    parent_id: str,
    parent_rows: list[dict[str, Any]],
    child_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Resolve only deterministic YouTube duplicate rows.

    A channel tab is never an individual source post.  It is therefore safe to
    remove a group containing *only* channel/tab rows.  When exactly one
    individual watch/short URL survives and the alternatives are incomplete
    landing rows, retain that one parent and repair children to its canonical
    URL.  Every other duplicate remains explicitly blocked for human review.
    """
    classes = [_youtube_url_class(str(row.get("canonical_post_url", ""))) for row in parent_rows]
    if not parent_rows or any(value == "other" for value in classes):
        return None

    ops: list[dict[str, Any]] = []
    if all(value == "landing" for value in classes):
        # These rows describe a channel surface, never a post.  Their media
        # children cannot have a valid individual parent, so remove both.
        for child in child_rows:
            ops.append({
                "operation": "DELETE_SOURCE_POST_MEDIA_ROW",
                "row_fingerprint": row_fingerprint(child),
                "source_post_media_id": str(child.get("source_post_media_id", "")),
                "reason": "YOUTUBE_LANDING_URL_NOT_A_SOURCE_POST",
            })
        for parent in parent_rows:
            ops.append({
                "operation": "DELETE_SOURCE_POST_ROW",
                "row_fingerprint": row_fingerprint(parent),
                "source_post_id": parent_id,
                "reason": "YOUTUBE_LANDING_URL_NOT_A_SOURCE_POST",
            })
    elif classes.count("individual") == 1 and all(value in {"individual", "landing"} for value in classes):
        keep = next(row for row, value in zip(parent_rows, classes) if value == "individual")
        canonical = _canonical_individual_youtube_url(str(keep.get("canonical_post_url", "")))
        if not canonical:
            return None
        for parent, value in zip(parent_rows, classes):
            if value == "landing":
                ops.append({
                    "operation": "DELETE_SOURCE_POST_ROW",
                    "row_fingerprint": row_fingerprint(parent),
                    "source_post_id": parent_id,
                    "reason": "INCOMPLETE_YOUTUBE_WATCH_URL",
                })
        for child in child_rows:
            if canonicalize_source_url(str(child.get("canonical_post_url", ""))) != canonical:
                ops.append({
                    "operation": "SET_CHILD_CANONICAL_URL_BY_FINGERPRINT",
                    "row_fingerprint": row_fingerprint(child),
                    "source_post_media_id": str(child.get("source_post_media_id", "")),
                    "to": canonical,
                    "reason": "ALIGN_CHILD_TO_RETAINED_INDIVIDUAL_VIDEO",
                })
    else:
        return None

    if not ops:
        return None
    return {
        "source_post_id": parent_id,
        "account_id": str(parent_rows[0].get("target_account_id", "")),
        "declared_media_count": 0,
        "actual_child_count": len(child_rows),
        "unique_media_index_count": len({str(row.get("media_index", "")) for row in child_rows}),
        "canonical_mismatch_child_ids": [],
        "duplicate_index_groups": [],
        "operations": ops,
        "blocker_codes": [],
        "apply_eligible": True,
        "parent_precondition_hash": "",
        "child_precondition_hashes": {},
        "resolution_kind": "DETERMINISTIC_YOUTUBE_DUPLICATE_REMEDIATION",
    }


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
        parent_rows = posts_by_id[parent_id]
        child_rows = children_by_id[parent_id]
        repair = plan_parent_repair(parent_id, parent_rows, child_rows)
        if "MULTIPLE_PARENTS" in repair["blocker_codes"]:
            safe_repair = _safe_duplicate_parent_repair(parent_id, parent_rows, child_rows)
            if safe_repair is not None:
                repair = safe_repair
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
        "operations": [repair.get("operations", []) for repair in repairs],
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
