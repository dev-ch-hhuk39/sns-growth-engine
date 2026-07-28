#!/usr/bin/env python3
"""Apply a reviewed source identity repair plan only behind explicit gates."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from source_identity_repair_executor import apply_plan_in_memory, production_apply_allowed
from source_identity_repair_contract import verify_identity_repair_outcome

TABLES = ("source_posts", "source_post_media")


def read_snapshot(client: Any) -> dict[str, list[dict[str, Any]]]:
    return {name: [dict(row) for row in client._ws(name).get_all_records()] for name in TABLES}


def _update_cell_by_id(client: Any, audit: dict[str, Any]) -> None:
    logical = audit["affected_row_type"] + "s" if audit["affected_row_type"] == "source_post" else "source_post_media"
    key = "source_post_id" if logical == "source_posts" else "source_post_media_id"
    ws = client._ws(logical)
    headers = ws.row_values(1)
    cell = ws.find(audit["affected_row_id"], in_column=headers.index(key) + 1)
    if cell is None or audit["field"] not in headers:
        raise RuntimeError("TARGET_ROW_OR_FIELD_NOT_FOUND")
    ws.update_cell(cell.row, headers.index(audit["field"]) + 1, audit["new_value"])


def apply_to_sheets(client: Any, plan: dict[str, Any]) -> dict[str, Any]:
    snapshot = read_snapshot(client)
    result = apply_plan_in_memory(plan, snapshot)
    if result["status"] != "APPLIED":
        return result
    applied: list[dict[str, Any]] = []
    try:
        for audit in result["audit_records"]:
            _update_cell_by_id(client, audit)
            applied.append(audit)
    except Exception as exc:
        return {**result, "status": "PARTIAL_FAILED", "reason": type(exc).__name__, "applied_audit_records": applied}
    after = read_snapshot(client)
    verified = verify_identity_repair_outcome(plan, after)
    return {**result, "read_after_write": verified, "status": "APPLIED" if verified["status"] == "PASS" else "PARTIAL_FAILED"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repair-plan", required=True, type=Path)
    parser.add_argument("--datasets", type=Path, help="required for dry-run; read-only export JSON")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-source-identity-repair", action="store_true")
    args = parser.parse_args()
    plan = json.loads(args.repair_plan.read_text(encoding="utf-8"))

    if not args.apply:
        if args.datasets is None:
            parser.error("--datasets is required for dry-run")
        result = apply_plan_in_memory(plan, json.loads(args.datasets.read_text(encoding="utf-8")))
        result["mode"] = "DRY_RUN_NO_SHEETS_WRITE"
    else:
        if not production_apply_allowed(apply=args.apply, confirm=args.confirm_source_identity_repair):
            result = {"status": "BLOCKED", "reason": "ALLOW_SHEETS_IDENTITY_REPAIR=true and --confirm-source-identity-repair are required", "mode": "APPLY_BLOCKED"}
        else:
            from config_loader import get_config
            from sheets_client import SheetsClient
            cfg = get_config()
            result = apply_to_sheets(SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False), plan)
            result["mode"] = "APPLY"
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "mode": result["mode"]}, ensure_ascii=False))
    return 0 if result["status"] == "APPLIED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
