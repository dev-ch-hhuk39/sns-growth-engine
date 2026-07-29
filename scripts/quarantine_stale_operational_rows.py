#!/usr/bin/env python3
"""Quarantine stale operational rows without deleting production history.

The default is a no-write inspection. Apply requires an explicit confirmation
and writes only a quarantine status/reason, preserving each original id so an
operator can reconcile ambiguous external publish state before retrying.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RULES = {
    "queue": ({"PROCESSING", "POSTED_SAVE_PENDING", "POSTED_SAVE_FAILED"}, "updated_at", "queue_id"),
    "content_slot_runs": ({"CLAIMED", "RUNNING"}, "lease_expires_at", "slot_run_id"),
    "media_assets": ({"DOWNLOADING", "UPLOADING", "PROCESSING"}, "updated_at", "media_asset_id"),
}


def _parse(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def build_plan(datasets: dict[str, list[dict[str, Any]]], *, older_than_minutes: int, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=max(1, older_than_minutes))
    operations: list[dict[str, str]] = []
    for logical, (statuses, timestamp_field, id_field) in RULES.items():
        for row in datasets.get(logical, []):
            status = str(row.get("status", "")).strip().upper()
            stamp = _parse(row.get(timestamp_field))
            if status not in statuses or stamp is None or stamp > cutoff:
                continue
            entity_id = str(row.get(id_field, "")).strip()
            if entity_id:
                operations.append({"tab": logical, "id_field": id_field, "entity_id": entity_id, "from_status": status, "to_status": "QUARANTINED", "reason": f"stale_{timestamp_field}"})
    return {"status": "PLAN_ONLY", "older_than_minutes": older_than_minutes, "operation_count": len(operations), "operations": operations}


def _records(client: Any, logical: str) -> list[dict[str, Any]]:
    return [dict(row) for row in client._ws(logical).get_all_records()]


def apply_plan(client: Any, plan: dict[str, Any]) -> dict[str, int]:
    updated = 0
    for operation in plan["operations"]:
        ws = client._ws(operation["tab"])
        headers = ws.row_values(1)
        rows = ws.get_all_records()
        row_number = next((index for index, row in enumerate(rows, start=2) if str(row.get(operation["id_field"], "")) == operation["entity_id"]), 0)
        if not row_number:
            raise RuntimeError(f"stale_row_missing:{operation['tab']}:{operation['entity_id']}")
        fields = {"status": "QUARANTINED"}
        if "quarantine_reason" in headers:
            fields["quarantine_reason"] = operation["reason"]
        if "quarantined_at" in headers:
            fields["quarantined_at"] = datetime.now(timezone.utc).isoformat()
        if "updated_at" in headers:
            fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        client._batch_update_fields(ws, headers, row_number, fields, label=f"quarantine:{operation['tab']}:{operation['entity_id']}")
        updated += 1
    return {"updated": updated}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--older-than-minutes", type=int, default=120)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-quarantine", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if args.apply and (not args.confirm_quarantine or not args.use_sheets):
        print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-quarantine --use-sheets"}))
        return 1
    if not args.use_sheets:
        print(json.dumps({"status": "PLAN_ONLY", "reason": "--use-sheets is required to inspect live operational rows", "would_write": False}))
        return 0
    from config_loader import get_config
    from sheets_client import SheetsClient
    cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=not args.apply)
    datasets = {logical: _records(client, logical) for logical in RULES}
    plan = build_plan(datasets, older_than_minutes=args.older_than_minutes)
    if not args.apply:
        print(json.dumps({**plan, "would_write": False}, ensure_ascii=False, indent=2)); return 0
    result = apply_plan(client, plan)
    print(json.dumps({"status": "APPLIED", **result, "operation_count": plan["operation_count"]}, ensure_ascii=False)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
