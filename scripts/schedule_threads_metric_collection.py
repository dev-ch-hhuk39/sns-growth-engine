#!/usr/bin/env python3
"""Plan the 24h/72h/7d Threads metrics collection lifecycle.

Default output is a pure plan. Writes require an explicit production gate and
are intentionally not used by scheduled workflows before final activation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
from accounts.managed_accounts import account_choices  # noqa: E402
from metrics_collection_schedule import build_metric_collection_jobs


def _load_input(path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not path:
        return [], []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return list(payload.get("posted_results", [])), list(payload.get("metrics_collection_jobs", []))


def main() -> int:
    parser = argparse.ArgumentParser(description="plan Threads metric collection jobs")
    parser.add_argument("--input-json", default="", help="offline posted_results/job fixture")
    parser.add_argument("--account-id", choices=account_choices(include_all=True), default="all")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-metrics-schedule", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    posted, existing = _load_input(args.input_json)
    if args.account_id != "all":
        posted = [row for row in posted if str(row.get("account_id", "")) == args.account_id]
        existing = [row for row in existing if str(row.get("account_id", "")) == args.account_id]
    jobs = build_metric_collection_jobs(posted, existing, now=datetime.now(timezone.utc))
    if not args.apply:
        print(json.dumps({"status": "PLAN_ONLY", "job_count": len(jobs), "jobs": jobs, "would_write": False}, ensure_ascii=False, indent=2))
        return 0
    if not args.confirm_metrics_schedule or os.environ.get("ALLOW_METRICS_SCHEDULE_WRITE") != "true":
        print(json.dumps({"status": "BLOCKED", "reason": "apply requires --confirm-metrics-schedule and ALLOW_METRICS_SCHEDULE_WRITE=true"}, ensure_ascii=False))
        return 1
    if not args.use_sheets:
        print(json.dumps({"status": "BLOCKED", "reason": "apply requires --use-sheets"}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "BLOCKED", "reason": "Sheets writer is reserved for final activation; use dry-run until approved", "job_count": len(jobs)}, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
