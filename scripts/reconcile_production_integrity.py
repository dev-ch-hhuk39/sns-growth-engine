#!/usr/bin/env python3
"""Reconcile historical queue/post integrity without deleting or fabricating data.

This command never fetches, downloads, uploads, transcribes, or publishes.
Duplicate queue rows are retained under unique audit IDs and blocked. Historical
posted rows lacking modern evidence are explicitly annotated and excluded from
future canary evidence; posted text, URLs, metrics, and status remain unchanged.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_config  # noqa: E402
from media.rights_policy import rights_allows_media_use  # noqa: E402
from sheets_client import TAB_DEFINITIONS, SheetsClient  # noqa: E402


FINAL_STATUS_PRIORITY = {
    "POSTED": 0,
    "POSTED_SAVE_FAILED": 1,
    "PROCESSING": 2,
    "READY": 3,
    "WAITING_REVIEW": 4,
    "PLANNED": 5,
}


def _true(value: Any) -> bool:
    return value is True or str(value or "").strip().lower() in {"1", "true", "yes"}


def _zero(value: Any) -> bool:
    try:
        return float(str(value).strip()) == 0.0
    except (TypeError, ValueError):
        return False


def _add_marker(value: Any, marker: str) -> str:
    existing = [part for part in str(value or "").split("|") if part and part != "PENDING"]
    if marker not in existing:
        existing.append(marker)
    return "|".join(existing)


def plan_queue_duplicate_repairs(
    rows: list[dict[str, Any]],
    *,
    business_date_jst: str | None = None,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for row_number, row in enumerate(rows, start=2):
        queue_id = str(row.get("queue_id", "")).strip()
        if queue_id:
            grouped.setdefault(queue_id, []).append((row_number, row))

    repairs: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()
    if business_date_jst is None:
        jst = timezone(timedelta(hours=9))
        business_date_jst = (datetime.now(jst) - timedelta(hours=4)).strftime("%Y%m%d")
    else:
        business_date_jst = business_date_jst.replace("-", "")
    for queue_id, entries in grouped.items():
        if len(entries) <= 1:
            continue
        ordered = sorted(
            entries,
            key=lambda item: (
                FINAL_STATUS_PRIORITY.get(str(item[1].get("status", "")).upper(), 99),
                item[0],
            ),
        )
        canonical_row = ordered[0][0]
        for row_number, _row in ordered[1:]:
            repairs.append({
                "row_number": row_number,
                "original_queue_id": queue_id,
                "canonical_row_number": canonical_row,
                "changes": {
                    "queue_id": f"{queue_id}__duplicate_row_{row_number}",
                    "status": "DUPLICATE_BLOCKED",
                    "auto_publish": "false",
                    "blocked_reason": f"duplicate_queue_id_reconciled; canonical_row={canonical_row}",
                    "updated_at": now,
                },
            })
    repaired_rows = {repair["row_number"] for repair in repairs}
    for row_number, row in enumerate(rows, start=2):
        if row_number in repaired_rows or str(row.get("status", "")).upper() != "READY":
            continue
        queue_id = str(row.get("queue_id", "")).strip()
        match = re.match(r"^slot_fallback_(\d{8})_", queue_id)
        if not match or match.group(1) >= business_date_jst:
            continue
        repairs.append({
            "row_number": row_number,
            "original_queue_id": queue_id,
            "canonical_row_number": row_number,
            "changes": {
                "status": "FAILED",
                "auto_publish": "false",
                "blocked_reason": "stale_slot_fallback_expired",
                "updated_at": now,
            },
        })
    return repairs


def plan_posted_annotations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    planned: dict[int, dict[str, Any]] = {}
    now = datetime.now(timezone.utc).isoformat()

    for row_number, row in enumerate(rows, start=2):
        if str(row.get("platform", "")).lower() != "threads" or str(row.get("status", "")).upper() != "POSTED":
            continue
        evidence_missing = _true(row.get("media_used")) and not (
            str(row.get("media_asset_id", "")).strip()
            and str(row.get("validator_status", "")).upper() == "PASS"
            and str(row.get("alignment_status", "")).upper() == "PASS"
            and _zero(row.get("unsupported_claim_count"))
        )
        if evidence_missing:
            planned[row_number] = {
                "row_number": row_number,
                "result_id": str(row.get("result_id", "")),
                "markers": ["HISTORICAL_MEDIA_EVIDENCE_MISSING"],
                "verification_status": _add_marker(
                    row.get("verification_status"), "HISTORICAL_MEDIA_EVIDENCE_MISSING"
                ),
            }

    duplicate_groups: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = {}
    for row_number, row in enumerate(rows, start=2):
        if str(row.get("platform", "")).lower() != "threads" or str(row.get("status", "")).upper() != "POSTED":
            continue
        text = str(row.get("posted_text", "")).strip()
        if text:
            duplicate_groups.setdefault((str(row.get("account_id", "")), text), []).append((row_number, row))
    for entries in duplicate_groups.values():
        if len(entries) <= 1:
            continue
        ordered = sorted(entries, key=lambda item: (str(item[1].get("posted_at", "")), str(item[1].get("result_id", ""))))
        for row_number, row in ordered[1:]:
            current = planned.get(row_number, {
                "row_number": row_number,
                "result_id": str(row.get("result_id", "")),
                "markers": [],
                "verification_status": str(row.get("verification_status", "")),
            })
            current["markers"].append("HISTORICAL_DUPLICATE_RECORDED")
            current["verification_status"] = _add_marker(
                current["verification_status"], "HISTORICAL_DUPLICATE_RECORDED"
            )
            planned[row_number] = current

    return [
        {
            **item,
            "changes": {
                "verification_status": item["verification_status"],
                "verification_checked_at": now,
            },
        }
        for _, item in sorted(planned.items())
    ]


def plan_stale_slot_run_recovery(
    rows: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    stale_after_minutes: int = 60,
) -> list[dict[str, Any]]:
    """Quarantine expired in-flight slots without creating a second claim.

    ``RECOVERY_REQUIRED`` is deliberately not auto-retried by the normal slot
    worker.  A later recovery workflow can make an explicit, auditable choice
    between a safe fallback and a no-post terminal record.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    repairs: list[dict[str, Any]] = []
    for row_number, row in enumerate(rows, start=2):
        if str(row.get("status", "")).upper() not in {"RUNNING", "CLAIMED", "PROCESSING"}:
            continue
        if str(row.get("actual_posted_at", "")).strip() or str(row.get("post_url", "")).strip():
            continue
        timestamp = str(row.get("lease_expires_at") or row.get("actual_started_at") or "").strip()
        try:
            observed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = observed.replace(tzinfo=timezone.utc)
        except ValueError:
            # Invalid timestamps are unsafe to reclaim.  Quarantine them too.
            observed = current - timedelta(minutes=stale_after_minutes + 1)
        is_expired_lease = bool(str(row.get("lease_expires_at", "")).strip()) and observed <= current
        is_stale_start = not str(row.get("lease_expires_at", "")).strip() and observed <= current - timedelta(minutes=stale_after_minutes)
        if not (is_expired_lease or is_stale_start):
            continue
        repairs.append({
            "row_number": row_number,
            "slot_run_id": str(row.get("slot_run_id", "")),
            "changes": {
                "status": "RECOVERY_REQUIRED",
                "claim_status": "EXPIRED",
                "lease_expires_at": "",
                "no_post_reason": "stale_slot_claim_requires_explicit_recovery",
                "last_error_redacted": "stale_slot_claim_expired",
                "updated_at": current.isoformat(),
            },
        })
    return repairs


def _media_ids(row: dict[str, Any]) -> set[str]:
    values = {
        str(row.get("media_asset_id", "")).strip(),
        str(row.get("media_id", "")).strip(),
    }
    raw = row.get("media_asset_ids_json")
    if raw:
        try:
            parsed = json.loads(str(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            parsed = []
        if isinstance(parsed, list):
            values.update(str(value).strip() for value in parsed)
    return {value for value in values if value}


def _uploaded_media(row: dict[str, Any]) -> bool:
    return bool(
        str(row.get("upload_status", "")).strip().upper() == "UPLOADED"
        or str(row.get("cloudinary_url", "")).strip()
        or (
            str(row.get("storage_provider", "")).strip().lower() == "cloudinary"
            and str(row.get("storage_url", "")).strip()
        )
    )


def _row_level_media_approved(row: dict[str, Any]) -> bool:
    rights = row.get("rights_status") or row.get("rights_policy")
    permission = str(row.get("permission_status", "")).strip().lower()
    approval = str(row.get("approval_status", "")).strip().upper()
    status = str(row.get("status", "")).strip().upper()
    reuse = str(row.get("reuse_status", "")).strip().lower()
    explicit_approval = approval == "APPROVED" or status in {
        "APPROVED", "READY", "SELF_GENERATED",
    } or reuse in {"approved", "approved_creator_clip"}
    if explicit_approval and rights_allows_media_use(rights) and permission in {
        "approved", "granted", "not_required",
    }:
        return True
    return (
        str(row.get("rights_policy", "")).strip().lower() == "owned"
        and status in {"APPROVED", "READY", "SELF_GENERATED"}
    )


def plan_inactive_media_quarantine(
    media_rows: list[dict[str, Any]],
    queue_rows: list[dict[str, Any]],
    posted_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Quarantine only inactive historical uploads with no usable approval.

    URLs and identifiers remain untouched for audit. A READY/PROCESSING queue
    or a non-historical POSTED result always protects its referenced assets.
    """
    active_ids: set[str] = set()
    for row in queue_rows:
        if str(row.get("status", "")).strip().upper() in {"READY", "PROCESSING"}:
            active_ids.update(_media_ids(row))
    for row in posted_rows:
        if str(row.get("status", "")).strip().upper() != "POSTED":
            continue
        if "HISTORICAL_MEDIA_EVIDENCE_MISSING" in str(row.get("verification_status", "")):
            continue
        active_ids.update(_media_ids(row))

    plans: list[dict[str, Any]] = []
    marker = "HISTORICAL_UNAPPROVED_UPLOAD_NOT_ACTIVE"
    for row_number, row in enumerate(media_rows, start=2):
        media_ids = _media_ids(row)
        if not media_ids or media_ids & active_ids:
            continue
        if not _uploaded_media(row) or _row_level_media_approved(row):
            continue
        if (
            str(row.get("reuse_status", "")).strip().upper() == "QUARANTINED"
            or str(row.get("upload_status", "")).strip().upper() == "QUARANTINED"
            or marker in str(row.get("notes", ""))
        ):
            continue
        plans.append({
            "row_number": row_number,
            "media_id": str(row.get("media_id", "")).strip(),
            "changes": {
                "reuse_status": "QUARANTINED",
                "allow_download": "false",
                "allow_cut": "false",
                "allow_upload": "false",
                "upload_status": "QUARANTINED",
                "notes": _add_marker(row.get("notes"), marker),
            },
        })
    return plans


def _read(client: SheetsClient, logical: str) -> tuple[Any, list[str], list[dict[str, Any]]]:
    ws = client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    headers = client._call_with_rate_limit_retry(f"headers:{logical}:reconcile", lambda: ws.row_values(1))
    rows = client._call_with_rate_limit_retry(f"rows:{logical}:reconcile", lambda: ws.get_all_records())
    return ws, headers, [dict(row) for row in rows]


def _apply_plans(
    client: SheetsClient,
    ws: Any,
    headers: list[str],
    plans: list[dict[str, Any]],
    *,
    label: str,
) -> None:
    ranges: list[dict[str, Any]] = []
    for plan in plans:
        row_number = int(plan["row_number"])
        for field, value in plan["changes"].items():
            if field not in headers:
                continue
            column = headers.index(field) + 1
            ranges.append({
                "range": f"{client._col_letter(column)}{row_number}",
                "values": [[str(value)]],
            })
    if not ranges:
        return

    def update_once():
        fresh = [
            {"range": item["range"], "values": [list(row) for row in item["values"]]}
            for item in ranges
        ]
        return ws.batch_update(fresh, value_input_option="USER_ENTERED")

    client._call_with_rate_limit_retry(label, update_once)


def main() -> int:
    parser = argparse.ArgumentParser(description="reconcile historical production integrity")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-reconcile", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.confirm_reconcile:
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-reconcile"}))
        return 1

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=not args.apply)
    queue_ws, queue_headers, queue_rows = _read(client, "queue")
    posted_ws, posted_headers, posted_rows = _read(client, "posted_results")
    slot_ws, slot_headers, slot_rows = _read(client, "content_slot_runs")
    media_ws, media_headers, media_rows = _read(client, "media_assets")
    queue_repairs = plan_queue_duplicate_repairs(queue_rows)
    posted_annotations = plan_posted_annotations(posted_rows)
    stale_slot_repairs = plan_stale_slot_run_recovery(slot_rows)
    inactive_media_quarantine = plan_inactive_media_quarantine(media_rows, queue_rows, posted_rows)
    result = {
        "status": "PLAN_ONLY" if not args.apply else "APPLYING",
        "queue_duplicate_row_repair_count": len(queue_repairs),
        "stale_slot_fallback_expired_count": sum(
            repair["changes"].get("blocked_reason") == "stale_slot_fallback_expired"
            for repair in queue_repairs
        ),
        "posted_annotation_count": len(posted_annotations),
        "stale_content_slot_recovery_count": len(stale_slot_repairs),
        "inactive_unapproved_media_quarantine_count": len(inactive_media_quarantine),
        "historical_media_evidence_missing_count": sum(
            "HISTORICAL_MEDIA_EVIDENCE_MISSING" in item["markers"] for item in posted_annotations
        ),
        "historical_duplicate_recorded_count": sum(
            "HISTORICAL_DUPLICATE_RECORDED" in item["markers"] for item in posted_annotations
        ),
        "would_publish": False,
    }
    if not args.apply:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    _apply_plans(client, queue_ws, queue_headers, queue_repairs, label="queue_reconcile_batch")
    _apply_plans(client, posted_ws, posted_headers, posted_annotations, label="posted_reconcile_batch")
    _apply_plans(client, slot_ws, slot_headers, stale_slot_repairs, label="content_slot_reconcile_batch")
    _apply_plans(
        client,
        media_ws,
        media_headers,
        inactive_media_quarantine,
        label="inactive_media_quarantine_batch",
    )
    result["status"] = "APPLIED"
    result["updated_queue_rows"] = len(queue_repairs)
    result["updated_posted_rows"] = len(posted_annotations)
    result["updated_content_slot_rows"] = len(stale_slot_repairs)
    result["updated_media_asset_rows"] = len(inactive_media_quarantine)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
