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

from config_loader import get_config
from sheets_client import TAB_DEFINITIONS, SheetsClient


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
    queue_repairs = plan_queue_duplicate_repairs(queue_rows)
    posted_annotations = plan_posted_annotations(posted_rows)
    result = {
        "status": "PLAN_ONLY" if not args.apply else "APPLYING",
        "queue_duplicate_row_repair_count": len(queue_repairs),
        "stale_slot_fallback_expired_count": sum(
            repair["changes"].get("blocked_reason") == "stale_slot_fallback_expired"
            for repair in queue_repairs
        ),
        "posted_annotation_count": len(posted_annotations),
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
    result["status"] = "APPLIED"
    result["updated_queue_rows"] = len(queue_repairs)
    result["updated_posted_rows"] = len(posted_annotations)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
