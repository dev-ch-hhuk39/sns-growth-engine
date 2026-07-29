#!/usr/bin/env python3
"""Safely ensure the two activation-evidence Sheets tabs and columns exist."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("posted_results", "metrics_collection_jobs")


def inspect(client: Any) -> dict[str, Any]:
    from sheets_client import TAB_DEFINITIONS
    report: dict[str, Any] = {"tabs": {}, "status": "PLAN_ONLY"}
    for logical in TARGETS:
        expected = list(TAB_DEFINITIONS[logical])
        try:
            ws = client._ws(logical); actual = ws.row_values(1)
            report["tabs"][logical] = {"exists": True, "missing_columns": [item for item in expected if item not in actual]}
        except Exception as exc:
            report["tabs"][logical] = {"exists": False, "missing_columns": expected, "reason": type(exc).__name__}
    report["status"] = "READ_OK" if all(item["exists"] and not item["missing_columns"] for item in report["tabs"].values()) else "SCHEMA_MISSING"
    return report


def ensure() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "src"))
    from config_loader import get_config
    from sheets_client import SheetsClient, TAB_DEFINITIONS
    cfg = get_config(); client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    before = inspect(client)
    for logical in TARGETS:
        client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    after = inspect(client)
    return {"status": "APPLIED" if after["status"] == "READ_OK" else "PARTIAL_FAILURE", "before": before, "read_after_write": after, "would_delete": False, "would_post": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-schema", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if not args.use_sheets:
        print(json.dumps({"status": "BLOCKED", "reason": "--use-sheets is required", "would_post": False})); return 1
    if args.apply:
        if not args.confirm_schema:
            print(json.dumps({"status": "BLOCKED", "reason": "--apply requires --confirm-schema", "would_post": False})); return 1
        result = ensure()
    else:
        try:
            sys.path.insert(0, str(ROOT / "src")); from config_loader import get_config; from sheets_client import SheetsClient
            cfg = get_config(); result = inspect(SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True))
        except Exception as exc:
            result = {"status": type(exc).__name__, "would_write": False, "would_post": False}
    result.setdefault("would_write", False); result.setdefault("would_post", False)
    print(json.dumps(result, ensure_ascii=False, indent=2)); return 0 if result.get("status") in {"READ_OK", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
