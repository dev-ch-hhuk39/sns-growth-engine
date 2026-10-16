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
from sheets_client import (  # noqa: E402
    SheetsMutationOutcomeUnknown, _col_letter, make_client, sheets_write_once,
)
from review_board_integrity import (  # noqa: E402
    ReviewBoardBlocked, index_review_rows, require_review_account_match,
)


def build_rows(queue_rows: list[dict], existing_rows: list[dict]) -> list[dict[str, str]]:
    # Never let duplicate queue IDs overwrite one another in a dict,
    # including across accounts. A reviewer decision belongs to one identity.
    queues = index_review_rows(queue_rows, source="QUEUE")
    existing = index_review_rows(existing_rows, source="REVIEW")
    require_review_account_match(existing, queues)
    return [
        review_row(queue, existing.get(queue_id))
        for queue_id, queue in queues.items()
        if is_reviewable(queue)
    ]


def sheets_call(client, label: str, operation):
    """Only SAFE reads get provider retries. Mutations use sheets_write_once."""
    retry = getattr(client, "_call_with_rate_limit_retry", None)
    return retry(label, operation) if callable(retry) else operation()


def sync(client, *, apply: bool) -> dict:
    if not hasattr(client, "_ws"):
        return {"status": "MOCK_PLAN", "would_write": 0, "review_rows": []}
    if apply and getattr(client, "dry_run", False):
        raise ReviewBoardBlocked("REVIEW_SYNC_DRY_RUN_CLIENT")
    # Unlike the previous path, a plan cannot create/resize a tab. Even on
    # apply, missing schema is an operator task, not implicit migration.
    queue_ws = client._ws("queue")
    review_ws = client._ws("publication_review")
    queue_rows = [
        dict(row) for row in sheets_call(
            client, "get_all_records:queue:publication_review_sync",
            queue_ws.get_all_records,
        )
    ]
    existing_rows = [
        dict(row) for row in sheets_call(
            client, "get_all_records:publication_review:sync_existing",
            review_ws.get_all_records,
        )
    ]
    rows = build_rows(queue_rows, existing_rows)
    plan = {
        "status": "PLAN_ONLY" if not apply else "APPLIED",
        "review_count": len(rows), "would_write": len(rows),
        "review_rows": rows,
    }
    if not apply:
        return plan
    headers = sheets_call(
        client, "row_values:publication_review:sync",
        lambda: review_ws.row_values(1),
    )
    if (not isinstance(headers, list) or len(headers) != len(set(headers))
            or not {"queue_id", "account_id", "review_decision", "reviewer_note",
                    "decision_applied_at", "decision_result"}.issubset(headers)):
        raise ReviewBoardBlocked("REVIEW_SYNC_SCHEMA_MISSING_OR_AMBIGUOUS")
    old = index_review_rows(existing_rows, source="REVIEW")
    by_queue = {
        text(row.get("queue_id")): index
        for index, row in enumerate(existing_rows, start=2)
        if text(row.get("queue_id"))
    }
    # Mutable reviewer cells are NEVER rewritten on an existing row.
    readonly = {"review_decision", "reviewer_note",
                "decision_applied_at", "decision_result"}
    updates, appends = [], []
    expected: dict[str, dict[str, str]] = {}
    for row in rows:
        if row["queue_id"] not in by_queue:
            appends.append([row.get(header, "") for header in headers])
            expected[row["queue_id"]] = {
                field: row.get(field, "") for field in headers
            }
            continue
        target_row = by_queue[row["queue_id"]]
        expected[row["queue_id"]] = {
            field: value for field, value in row.items()
            if field in headers and field not in readonly
        }
        for field, value in expected[row["queue_id"]].items():
            updates.append({
                "range": f"{_col_letter(headers.index(field) + 1)}{target_row}",
                "values": [[value]],
            })
    # Google Sheets writes are non-idempotent and can ACK after a timeout.
    # Never run the generic 429/5xx retry helper on mutation calls.
    if appends:
        sheets_write_once(
            "append_rows:publication_review:sync",
            lambda: review_ws.append_rows(appends, value_input_option="RAW"),
        )
    if updates:
        sheets_write_once(
            "batch_update:publication_review:sync",
            lambda: review_ws.batch_update(updates, value_input_option="RAW"),
        )
    try:
        after = [
            dict(row) for row in sheets_call(
                client, "get_all_records:publication_review:sync_verify",
                review_ws.get_all_records,
            )
        ]
        saved = index_review_rows(after, source="REVIEW")
        require_review_account_match(saved, index_review_rows(queue_rows, source="QUEUE"))
        valid = all(
            identity in saved and all(
                text(saved[identity].get(field)) == text(value)
                for field, value in fields.items()
            )
            for identity, fields in expected.items()
        )
    except ReviewBoardBlocked:
        raise SheetsMutationOutcomeUnknown(
            "review_sync_identity_readback_unknown_manual_reconciliation"
        ) from None
    except Exception:
        raise SheetsMutationOutcomeUnknown(
            "review_sync_readback_unknown_manual_reconciliation"
        ) from None
    if not valid:
        raise SheetsMutationOutcomeUnknown(
            "review_sync_readback_mismatch_manual_reconciliation"
        )
    plan["read_after_write"] = True
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
    if args.apply and not args.use_sheets:
        raise SystemExit("BLOCKED: --apply requires --use-sheets (no mock success)")
    client = make_client(get_config(), dry_run=not args.apply, force_mock=not args.use_sheets)
    result = sync(client, apply=args.apply)
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "review_rows"}, ensure_ascii=False))
    return 2 if args.apply and result.get("status") != "APPLIED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
