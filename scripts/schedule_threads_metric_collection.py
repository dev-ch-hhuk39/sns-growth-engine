#!/usr/bin/env python3
"""Inspect metric reservations and explicitly repair one verified Threads result.

Default is read-only. Apply requires a single current-scope account/result,
confirmation and the existing environment gate. No SNS API, schema creation,
job reset, scheduler activation or queue mutation is performed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
from accounts.managed_accounts import account_choices  # noqa: E402
from metrics_reservations import (  # noqa: E402
    ReservationBlocked, plan_reservations, read_table, reserve_metrics,
)

REPAIR_ACCOUNTS = {"night_scout", "liver_manager"}


def _load_input(path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not path:
        return [], []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return list(payload.get("posted_results", [])), list(payload.get("metrics_collection_jobs", []))


def load_client(*, apply: bool):
    from config_loader import get_config
    from sheets_client import SheetsClient

    cfg = get_config()
    return SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=not apply)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-json", default="", help="offline posted_results/job fixture; never applied")
    parser.add_argument("--account-id", choices=account_choices(include_all=True), default="all")
    parser.add_argument("--result-id", default="", help="required exact result for repair")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-metrics-schedule", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    try:
        # Validate before loading any production configuration or connecting.
        if args.dry_run and args.apply:
            raise ReservationBlocked("dry_run_and_apply_are_mutually_exclusive")
        if args.input_json and (args.apply or args.use_sheets):
            raise ReservationBlocked("offline_fixture_cannot_authorize_live_repair")
        if args.apply:
            if (not args.confirm_metrics_schedule
                    or os.environ.get("ALLOW_METRICS_SCHEDULE_WRITE") != "true"):
                raise ReservationBlocked("apply_requires_confirmation_and_environment_gate")
            if not args.use_sheets:
                raise ReservationBlocked("apply_requires_use_sheets")
            if args.account_id not in REPAIR_ACCOUNTS or not args.result_id:
                raise ReservationBlocked("apply_requires_one_supported_account_and_result")
        client = load_client(apply=args.apply) if args.use_sheets else None
        if args.apply:
            result = reserve_metrics(client, account_id=args.account_id,
                                     result_id=args.result_id, apply=True)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if client is not None:
            _, posted = read_table(client, "posted_results")
            _, existing = read_table(client, "metrics_collection_jobs")
        else:
            posted, existing = _load_input(args.input_json)
        selected = [r for r in posted
                    if (args.account_id == "all" or str(r.get("account_id", "")) == args.account_id)
                    and (not args.result_id or str(r.get("result_id", "")) == args.result_id)]
        plans, blocked = [], []
        if args.result_id and not selected:
            raise ReservationBlocked("posted_result_missing_or_ambiguous")
        for row in selected:
            account_id, result_id = str(row.get("account_id", "")), str(row.get("result_id", ""))
            try:
                plans.append(plan_reservations(posted, existing, account_id=account_id, result_id=result_id))
            except ReservationBlocked as exc:
                blocked.append({"account_id": account_id, "result_id": result_id, "reason": str(exc)})
        jobs = [job for plan in plans for job in plan["jobs"]]
        print(json.dumps({"status": "BLOCKED" if blocked else "PLAN_ONLY", "job_count": len(jobs),
                          "jobs": jobs, "plans": plans, "blocked": blocked, "would_write": False},
                         ensure_ascii=False, indent=2))
        return 1 if blocked else 0
    except ReservationBlocked as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc), "would_post": False}))
        return 1
    except Exception:
        print(json.dumps({"status": "BLOCKED", "reason": "reservation_operation_failed", "would_post": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
