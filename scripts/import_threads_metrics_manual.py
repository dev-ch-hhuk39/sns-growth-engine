#!/usr/bin/env python3
"""Import manually collected Threads metrics into posted_results."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_config  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ws(client: SheetsClient, logical: str):
    return client._ws(logical)


def append_row(client: SheetsClient, logical: str, row: dict[str, Any]) -> None:
    sheet = ws(client, logical)
    headers = sheet.row_values(1)
    sheet.append_row([str(row.get(h, "")) for h in headers], value_input_option="USER_ENTERED")


def update_posted_result(client: SheetsClient, result_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    sheet = ws(client, "posted_results")
    headers = sheet.row_values(1)
    if "result_id" not in headers:
        raise KeyError("posted_results.result_id header missing")
    cell = sheet.find(result_id, in_column=headers.index("result_id") + 1)
    if cell is None:
        raise KeyError(f"result_id={result_id!r} not found")
    rows = sheet.get_all_records()
    existing = dict(rows[cell.row - 2])
    for field, value in fields.items():
        if field in headers:
            sheet.update_cell(cell.row, headers.index(field) + 1, str(value))
    return {**existing, **fields}


def log_event(client: SheetsClient, account_id: str, result_id: str, memo: str) -> None:
    append_row(client, "logs", {
        "log_id": f"metrics_import_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "timestamp": now_iso(),
        "account_id": account_id,
        "operation": "import_threads_metrics_manual",
        "level": "INFO",
        "status": "MEASURED",
        "message": f"Manual Threads metrics imported result_id={result_id}",
        "details": memo,
    })


def save_pdca(client: SheetsClient, row: dict[str, Any], memo: str) -> None:
    result_id = str(row.get("result_id", ""))
    account_id = str(row.get("account_id", ""))
    likes = int(str(row.get("likes", "0") or "0"))
    comments = int(str(row.get("comments", "0") or "0"))
    views = int(str(row.get("views", "0") or "0"))
    er = round((likes + comments) / views, 4) if views > 0 else 0
    created_at = now_iso()
    append_row(client, "pdca_runs", {
        "run_id": f"pdca_metrics_{result_id}",
        "account_id": account_id,
        "platform": "threads",
        "days": "manual",
        "total_results": "1",
        "suggestion_count": "1",
        "next_jobs_count": "1",
        "best_content_type": "manual_metric_import",
        "best_er": str(er),
        "created_at": created_at,
        "notes": f"Manual metrics import. {memo}",
    })
    append_row(client, "prompt_improvement_suggestions", {
        "suggestion_id": f"sug_metrics_{result_id}",
        "account_id": account_id,
        "created_at": created_at,
        "source": "import_threads_metrics_manual",
        "suggestion_type": "strategy_review",
        "target_template": "",
        "current_behavior": "Manual metrics imported.",
        "suggested_change": "Review metrics before changing prompt or queue policy.",
        "reason": f"views={views} likes={likes} comments={comments} er={er}",
        "expected_impact": "Human-reviewed PDCA only.",
        "priority": "medium",
        "status": "WAITING_REVIEW",
        "reviewed_by": "",
        "reviewed_at": "",
        "notes": "auto_apply=false; learning_rules remain inactive.",
    })


def main() -> int:
    parser = argparse.ArgumentParser(description="Import manual Threads metrics")
    parser.add_argument("--result-id", required=True)
    parser.add_argument("--views", type=int, required=True)
    parser.add_argument("--likes", type=int, required=True)
    parser.add_argument("--comments", type=int, required=True)
    parser.add_argument("--follows", type=int, required=True)
    parser.add_argument("--profile-clicks", type=int, default=0)
    parser.add_argument("--line-adds", type=int, default=0)
    parser.add_argument("--memo", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if min(args.views, args.likes, args.comments, args.follows, args.profile_clicks, args.line_adds) < 0:
        print("[ERROR] metrics must be >= 0")
        return 1

    fields = {
        "views": args.views,
        "likes": args.likes,
        "comments": args.comments,
        "follows": args.follows,
        "profile_clicks": args.profile_clicks,
        "line_adds": args.line_adds,
        "metrics_status": "MEASURED",
        "collected_at": now_iso(),
        "manual_memo": args.memo,
    }
    if args.dry_run:
        print(json.dumps({"dry_run": True, "result_id": args.result_id, "fields": fields}, ensure_ascii=False))
        return 0

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    updated = update_posted_result(client, args.result_id, fields)
    log_event(client, str(updated.get("account_id", "")), args.result_id, args.memo)
    save_pdca(client, updated, args.memo)
    print(json.dumps({
        "status": "MEASURED",
        "result_id": args.result_id,
        "account_id": updated.get("account_id", ""),
        "metrics_status": "MEASURED",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
