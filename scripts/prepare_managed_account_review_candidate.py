#!/usr/bin/env python3
"""Create one account-scoped WAITING_REVIEW text candidate; never publishes."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from accounts.managed_accounts import managed_account  # noqa: E402
from create_missing_text_canaries import _append, build_rows  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--content-type", default="original_text")
    parser.add_argument("--slot-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-prepare", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    account = managed_account(args.account_id)
    if args.content_type not in set(account.get("scheduled_routes", [])):
        print(json.dumps({"status": "BLOCKED", "reason": "route_not_scheduled_for_account", "would_post": False}))
        return 1
    if args.apply and (not args.confirm_prepare or not args.use_sheets):
        print(json.dumps({"status": "BLOCKED", "reason": "apply_requires_confirm_and_sheets", "would_post": False}))
        return 1

    existing: list[dict] = []
    posted: list[dict] = []
    client = None
    if args.use_sheets:
        from config_loader import get_config
        from sheets_client import SheetsClient, TAB_DEFINITIONS

        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=not args.apply)
        for logical, target in (("queue", existing), ("posted_results", posted)):
            try:
                client._ensure_tab(logical, TAB_DEFINITIONS[logical])
                target.extend(client._ws(logical).get_all_records())
            except Exception:
                if args.apply:
                    raise
    batch_id = f"managed_{args.account_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    result = build_rows(
        existing,
        posted,
        targets=((args.account_id, args.content_type),),
        batch_id=batch_id,
    )
    rows = list(result.get("rows", []))
    for row in rows:
        row["slot_id"] = args.slot_id
        row["status"] = "WAITING_REVIEW"
        row["human_review_required"] = "true"
    if args.apply and result.get("status") == "PLAN_ONLY":
        assert client is not None
        applied = _append(client, rows)
        result = {**result, **applied, "rows": rows}
    result["would_post"] = False
    result["review_policy"] = account.get("review_policy", "")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") in {"PLAN_ONLY", "APPLIED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
