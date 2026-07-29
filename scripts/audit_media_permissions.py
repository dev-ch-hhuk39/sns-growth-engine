#!/usr/bin/env python3
"""Read-only audit of the media permission ledger and owner-input gaps."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from final_production_contracts import permission_deficits, required_owner_inputs


def _sources() -> list[dict[str, Any]]:
    return list(json.loads((ROOT / "config/source_accounts/default_sources.json").read_text(encoding="utf-8")).get("sources", []))


def _permissions(use_sheets: bool) -> tuple[list[dict[str, Any]], str]:
    if not use_sheets:
        return [], "use_sheets_required_for_live_ledger"
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=True)
        return [dict(row) for row in client._ws("media_permissions").get_all_records()], "READ_OK"
    except Exception as exc:
        return [], f"{type(exc).__name__}"


def build_report(*, use_sheets: bool) -> dict[str, Any]:
    permissions, ledger_status = _permissions(use_sheets)
    deficits = permission_deficits(_sources(), permissions)
    return {
        "status": "READ_OK" if ledger_status == "READ_OK" else "PLAN_ONLY",
        "ledger_status": ledger_status,
        "permission_row_count": len(permissions),
        "deficit_count": len(deficits),
        "deficits": deficits,
        "required_owner_inputs": required_owner_inputs(deficits),
        "would_write": False,
        "would_download": False,
        "would_upload": False,
        "would_post": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--write-required-owner-inputs", type=Path, default=None)
    args = parser.parse_args()
    report = build_report(use_sheets=args.use_sheets)
    if args.write_required_owner_inputs:
        args.write_required_owner_inputs.parent.mkdir(parents=True, exist_ok=True)
        args.write_required_owner_inputs.write_text(json.dumps(report["required_owner_inputs"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["required_owner_inputs_path"] = str(args.write_required_owner_inputs)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
