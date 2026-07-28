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
from source_identity_repair_contract import row_fingerprint, verify_identity_repair_outcome

TABLES = ("source_posts", "source_post_media")


def read_snapshot(client: Any) -> dict[str, list[dict[str, Any]]]:
    return {name: [dict(row) for row in client._ws(name).get_all_records()] for name in TABLES}


def _worksheet_for_audit(client: Any, audit: dict[str, Any]):
    logical = audit["affected_row_type"] + "s" if audit["affected_row_type"] == "source_post" else "source_post_media"
    return logical, client._ws(logical)


def _find_sheet_row_by_fingerprint(ws: Any, fingerprint: str) -> tuple[int, list[str], list[str]]:
    values = ws.get_all_values()
    if not values:
        raise RuntimeError("HEADER_ROW_MISSING")
    headers = values[0]
    matches = []
    for row_number, values_row in enumerate(values[1:], start=2):
        padded = list(values_row) + [""] * (len(headers) - len(values_row))
        row = {header: padded[index] for index, header in enumerate(headers) if header}
        if row_fingerprint(row) == fingerprint:
            matches.append((row_number, headers, padded))
    if len(matches) != 1:
        raise RuntimeError("TARGET_ROW_FINGERPRINT_NOT_UNIQUELY_RESOLVABLE")
    return matches[0]


def _update_cell_by_audit(client: Any, audit: dict[str, Any]) -> None:
    _, ws = _worksheet_for_audit(client, audit)
    if not audit.get("row_fingerprint"):
        raise RuntimeError("ROW_FINGERPRINT_REQUIRED_FOR_SHEETS_APPLY")
    row_number, headers, _ = _find_sheet_row_by_fingerprint(ws, str(audit["row_fingerprint"]))
    if audit["field"] not in headers:
        raise RuntimeError("TARGET_ROW_OR_FIELD_NOT_FOUND")
    ws.update_cell(row_number, headers.index(audit["field"]) + 1, audit["new_value"])


def _delete_row_by_audit(client: Any, audit: dict[str, Any]) -> dict[str, Any]:
    _, ws = _worksheet_for_audit(client, audit)
    row_number, headers, values = _find_sheet_row_by_fingerprint(ws, str(audit["row_fingerprint"]))
    ws.delete_rows(row_number)
    return {"logical": "source_posts" if audit["affected_row_type"] == "source_post" else "source_post_media", "row_number": row_number, "headers": headers, "values": values}


def _rollback_applied(client: Any, applied: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for item in reversed(applied):
        try:
            audit, receipt = item["audit"], item.get("receipt", {})
            _, ws = _worksheet_for_audit(client, audit)
            if audit["field"] == "__row__":
                ws.insert_row(receipt["values"], index=receipt["row_number"], value_input_option="USER_ENTERED")
            else:
                row_number, headers, _ = _find_sheet_row_by_fingerprint(ws, str(audit["row_fingerprint"]))
                ws.update_cell(row_number, headers.index(audit["field"]) + 1, audit["old_value"])
        except Exception as exc:
            errors.append(type(exc).__name__)
    return errors


def apply_to_sheets(client: Any, plan: dict[str, Any]) -> dict[str, Any]:
    snapshot = read_snapshot(client)
    result = apply_plan_in_memory(plan, snapshot)
    if result["status"] != "APPLIED":
        return result
    applied: list[dict[str, Any]] = []
    try:
        for audit in result["audit_records"]:
            receipt = _delete_row_by_audit(client, audit) if audit["field"] == "__row__" else _update_cell_by_audit(client, audit)
            applied.append({"audit": audit, "receipt": receipt})
    except Exception as exc:
        rollback_errors = _rollback_applied(client, applied)
        return {**result, "status": "PARTIAL_FAILED", "reason": type(exc).__name__, "error": str(exc), "applied_audit_records": [item["audit"] for item in applied], "rollback_attempted": True, "rollback_errors": rollback_errors}
    after = read_snapshot(client)
    verified = verify_identity_repair_outcome(plan, after)
    if verified["status"] == "PASS":
        client.log("source_identity_repair", "APPLIED", "Source identity repair verified", details=json.dumps({"repair_plan_id": plan.get("repair_plan_id", ""), "operation_count": len(result["audit_records"]), "before_hashes": [r.get("old_value", "") for r in result["audit_records"]], "after_verifier": "PASS"}, ensure_ascii=True))
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
