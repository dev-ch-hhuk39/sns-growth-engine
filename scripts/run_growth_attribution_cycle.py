#!/usr/bin/env python3
"""Explain measured post outcomes and update bounded generation strategy state.

The cycle is read-only by default. Apply writes only attribution evidence and
bounded strategy rows. It never posts, changes queue status, or rewrites prompts.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from learning.feature_attribution import build_growth_cycle  # noqa: E402
from accounts.managed_accounts import account_choices  # noqa: E402


def _read_tab(client: Any, logical: str) -> list[dict[str, Any]]:
    try:
        return [dict(row) for row in client._ws(logical).get_all_records()]
    except Exception:
        return []


def _upsert_rows(client: Any, logical: str, key: str, rows: list[dict[str, Any]]) -> dict[str, int]:
    from gspread.utils import rowcol_to_a1
    from sheets_client import TAB_DEFINITIONS

    ws = client._ensure_tab(logical, TAB_DEFINITIONS[logical])
    headers = ws.row_values(1)
    existing = {
        str(row.get(key, "")): (index, dict(row))
        for index, row in enumerate(ws.get_all_records(), start=2)
        if str(row.get(key, ""))
    }
    updates: list[dict[str, Any]] = []
    appends: list[list[str]] = []
    created = updated = 0
    for row in rows:
        identity = str(row.get(key, ""))
        if not identity:
            continue
        if identity in existing:
            row_number, old = existing[identity]
            merged = {**old, **row}
            updates.append({
                "range": f"{rowcol_to_a1(row_number, 1)}:{rowcol_to_a1(row_number, len(headers))}",
                "values": [[str(merged.get(header, "")) for header in headers]],
            })
            updated += 1
        else:
            appends.append([str(row.get(header, "")) for header in headers])
            created += 1
    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")
    if appends:
        ws.append_rows(appends, value_input_option="USER_ENTERED")
    return {"created": created, "updated": updated}


def _load_input(path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return list(data.get("posted_results", [])), list(data.get("metric_snapshots", []))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--account-id",
        default="all",
        choices=account_choices(include_all=True),
    )
    parser.add_argument("--input-json", help="Offline input containing posted_results and metric_snapshots")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-attribution", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    client = None
    if args.input_json:
        posted, snapshots = _load_input(args.input_json)
    elif args.use_sheets:
        from config_loader import get_config
        from sheets_client import SheetsClient
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=not args.apply)
        posted = _read_tab(client, "posted_results")
        snapshots = _read_tab(client, "metric_snapshots")
    else:
        print(json.dumps({"status": "BLOCKED", "reason": "--input-json or --use-sheets is required"}, ensure_ascii=False))
        return 1

    result = build_growth_cycle(posted, snapshots, account_id=args.account_id)
    result["would_write"] = False
    result["would_post"] = False
    result["would_rewrite_prompts"] = False

    if args.apply:
        if not args.confirm_attribution:
            result = {"status": "BLOCKED", "reason": "--apply requires --confirm-attribution", "would_post": False}
        elif client is None:
            result = {"status": "BLOCKED", "reason": "--apply requires --use-sheets", "would_post": False}
        else:
            from sheets_client import TAB_DEFINITIONS
            # Keep queue/result feature columns current before the next posting
            # window so measured attribution never loses provenance.
            client._ensure_tab("queue", TAB_DEFINITIONS["queue"])
            client._ensure_tab("posted_results", TAB_DEFINITIONS["posted_results"])
            attribution_ops = _upsert_rows(client, "post_attributions", "attribution_id", result["attributions"])
            strategy_ops = _upsert_rows(client, "strategy_state", "strategy_id", result["strategy_state"])
            result.update({
                "status": "APPLIED",
                "would_write": True,
                "attribution_operations": attribution_ops,
                "strategy_operations": strategy_ops,
            })

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"PLAN_ONLY", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
