#!/usr/bin/env python3
"""Sync reviewable Threads queue rows into the human-facing 投稿レビュー tab.

The command does not post, fetch, download, cut, or upload. It preserves the
operator's review_decision and reviewer_note cells on every sync.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from config_loader import get_config  # noqa: E402
from publication_review_board import is_reviewable, review_row, text  # noqa: E402
from sheets_client import TAB_DEFINITIONS, _col_letter, make_client  # noqa: E402


def build_rows(queue_rows: list[dict], existing_rows: list[dict]) -> list[dict[str, str]]:
    existing = {text(row.get("queue_id")): row for row in existing_rows if text(row.get("queue_id"))}
    return [review_row(queue, existing.get(text(queue.get("queue_id")))) for queue in queue_rows if is_reviewable(queue)]


def sheets_call(client, label: str, operation):
    retry = getattr(client, "_call_with_rate_limit_retry", None)
    return retry(label, operation) if callable(retry) else operation()


def sync(client, *, apply: bool) -> dict:
    if not hasattr(client, "_ensure_tab") or not hasattr(client, "_ws"):
        return {"status": "MOCK_PLAN", "would_write": 0, "review_rows": []}
    client._ensure_tab("queue", TAB_DEFINITIONS["queue"])
    if apply:
        client._ensure_tab("publication_review", TAB_DEFINITIONS["publication_review"])
    queue_rows = [
        dict(row)
        for row in sheets_call(
            client,
            "get_all_records:queue:publication_review_sync",
            lambda: client._ws("queue").get_all_records(),
        )
    ]
    try:
        existing_rows = [
            dict(row)
            for row in sheets_call(
                client,
                "get_all_records:publication_review:sync_existing",
                lambda: client._ws("publication_review").get_all_records(),
            )
        ]
    except Exception:
        existing_rows = []
    rows = build_rows(queue_rows, existing_rows)
    plan = {"status": "PLAN_ONLY" if not apply else "APPLIED", "review_count": len(rows), "would_write": len(rows), "review_rows": rows}
    if not apply:
        return plan
    ws = client._ws("publication_review")
    headers = sheets_call(
        client,
        "row_values:publication_review:sync",
        lambda: ws.row_values(1),
    )
    by_queue = {text(row.get("queue_id")): index for index, row in enumerate(existing_rows, start=2) if text(row.get("queue_id"))}
    updates, appends = [], []
    for row in rows:
        if row["queue_id"] not in by_queue:
            appends.append([row.get(header, "") for header in headers])
            continue
        target_row = by_queue[row["queue_id"]]
        for field, value in row.items():
            if field in {"review_decision", "reviewer_note", "decision_applied_at", "decision_result"} or field not in headers:
                continue
            updates.append({"range": f"{_col_letter(headers.index(field) + 1)}{target_row}", "values": [[value]]})
    if appends:
        sheets_call(
            client,
            "append_rows:publication_review:sync",
            lambda: ws.append_rows(appends, value_input_option="USER_ENTERED"),
        )
    if updates:
        sheets_call(
            client,
            "batch_update:publication_review:sync",
            lambda: ws.batch_update(updates, value_input_option="USER_ENTERED"),
        )
    saved = {
        text(row.get("queue_id"))
        for row in sheets_call(
            client,
            "get_all_records:publication_review:sync_verify",
            lambda: client._ws("publication_review").get_all_records(),
        )
    }
    plan["read_after_write"] = all(row["queue_id"] in saved for row in rows)
    plan["appended_count"] = len(appends)
    plan["updated_count"] = len(updates)
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-review-sync", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.apply and not args.confirm_review_sync:
        raise SystemExit("BLOCKED: --apply requires --confirm-review-sync")
    client = make_client(get_config(), dry_run=not args.apply, force_mock=not args.use_sheets)
    result = sync(client, apply=args.apply)
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "review_rows"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
