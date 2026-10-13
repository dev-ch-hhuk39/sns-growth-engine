#!/usr/bin/env python3
"""Apply explicit 投稿レビュー decisions to queue rows; never posts directly."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from config_loader import get_config  # noqa: E402
from publication_review_board import decision_for_row, now_iso, text  # noqa: E402
from sheets_client import (  # noqa: E402
    SheetsMutationOutcomeUnknown, _col_letter, make_client, sheets_write_once,
)
from review_board_integrity import (  # noqa: E402
    ReviewBoardBlocked, index_review_rows, require_review_account_match,
    require_fresh_decision_evidence,
)


def build_decisions(
    review_rows: list[dict], queue_rows: list[dict],
    *, allow_media_posts: bool, strict_trusted_media_review: bool = False,
) -> list[tuple[dict, dict, str, dict[str, str]]]:
    queues = index_review_rows(queue_rows, source="QUEUE")
    reviews = index_review_rows(review_rows, source="REVIEW")
    require_review_account_match(reviews, queues)
    result = []
    for review_id, review in reviews.items():
        queue = queues.get(review_id)
        if queue is None:
            continue
        outcome, fields = decision_for_row(
            review, queue, allow_media_posts=allow_media_posts,
            strict_trusted_media_review=strict_trusted_media_review,
        )
        if outcome != "SKIP":
            try:
                require_fresh_decision_evidence(
                    review, queue, selected_fields=fields,
                )
            except ReviewBoardBlocked:
                outcome, fields = "BLOCKED_STALE_REVIEW", {}
            result.append((review, queue, outcome, fields))
    return result


def apply(client, *, do_apply: bool, allow_media_posts: bool,
          strict_trusted_media_review: bool = False) -> dict:
    if not hasattr(client, "_ws"):
        return {"status": "MOCK_PLAN", "decision_count": 0}
    if do_apply and getattr(client, "dry_run", False):
        raise ReviewBoardBlocked("REVIEW_DECISION_DRY_RUN_CLIENT")
    # A read-only plan must never mutate the destination schema; and an
    # approved apply requires the worksheet to exist, not create it silently.
    queue_ws = client._ws("queue")
    review_ws = client._ws("publication_review")
    queue_rows = [dict(row) for row in queue_ws.get_all_records()]
    review_rows = [dict(row) for row in review_ws.get_all_records()]
    plans = build_decisions(
        review_rows, queue_rows,
        allow_media_posts=allow_media_posts,
        strict_trusted_media_review=strict_trusted_media_review,
    )
    report = {
        "status": "APPLIED" if do_apply else "PLAN_ONLY",
        "decision_count": len(plans),
        "outcomes": [outcome for _, _, outcome, _ in plans],
    }
    if not do_apply:
        return report
    review_headers = review_ws.row_values(1)
    if (not isinstance(review_headers, list)
            or len(review_headers) != len(set(review_headers))
            or not {"queue_id", "decision_result", "decision_applied_at",
                    "review_status"}.issubset(review_headers)):
        raise ReviewBoardBlocked("REVIEW_DECISION_SCHEMA_INVALID")
    review_by_queue = {
        text(row.get("queue_id")): index
        for index, row in enumerate(review_rows, start=2)
        if text(row.get("queue_id"))
    }
    review_updates = []
    review_expected: dict[str, dict[str, str]] = {}
    updated_fields: dict[str, dict[str, str]] = {}
    for review, queue, outcome, fields in plans:
        queue_id = text(queue.get("queue_id"))
        if fields:
            updated_fields[queue_id] = fields
        row_no = review_by_queue.get(queue_id)
        if row_no is None:
            raise ReviewBoardBlocked("REVIEW_DECISION_ROW_MISSING")
        changed = {
            "decision_result": outcome,
            "decision_applied_at": now_iso(),
            "review_status": "APPROVED" if outcome == "READY" else outcome,
        }
        review_expected[queue_id] = changed
        for field, value in changed.items():
            review_updates.append({
                "range": f"{_col_letter(review_headers.index(field) + 1)}{row_no}",
                "values": [[value]],
            })
    # Strict ID checks happen before any mutation. Queue row changes are
    # internally verified by SheetsClient; the review log is another Sheets
    # request and cannot be atomically committed together with queue rows.
    for queue_id, fields in updated_fields.items():
        client.update_queue_item(queue_id, **fields)
    if review_updates:
        sheets_write_once(
            "publication_review_decision_update",
            lambda: review_ws.batch_update(
                review_updates, value_input_option="RAW",
            ),
        )
    try:
        saved_queue = index_review_rows(
            [dict(row) for row in queue_ws.get_all_records()], source="QUEUE",
        )
        saved_review = index_review_rows(
            [dict(row) for row in review_ws.get_all_records()], source="REVIEW",
        )
        require_review_account_match(saved_review, saved_queue)
        queue_ok = all(
            queue_id in saved_queue and all(
                text(saved_queue[queue_id].get(field)) == text(value)
                for field, value in changed.items()
            ) for queue_id, changed in updated_fields.items()
        )
        review_ok = all(
            queue_id in saved_review and all(
                text(saved_review[queue_id].get(field)) == text(value)
                for field, value in changed.items()
            ) for queue_id, changed in review_expected.items()
        )
    except Exception:
        raise SheetsMutationOutcomeUnknown(
            "publication_review_decision_readback_unknown_manual_reconciliation"
        ) from None
    if not queue_ok or not review_ok:
        raise SheetsMutationOutcomeUnknown(
            "publication_review_decision_readback_mismatch_manual_reconciliation"
        )
    report["queue_read_after_write"] = True
    report["review_read_after_write"] = True
    report["updated_queue_ids"] = list(updated_fields)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-review-decisions", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument(
        "--require-trusted-media-review",
        action="store_true",
        help="Fail closed on legacy media READY transitions (requires future authenticated service)",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.apply and not args.confirm_review_decisions:
        raise SystemExit("BLOCKED: --apply requires --confirm-review-decisions")
    if args.apply and not args.use_sheets:
        raise SystemExit("BLOCKED: --apply requires --use-sheets (no mock success)")
    cfg = get_config()
    autonomous = __import__("json").loads((ROOT / "config" / "autonomous_mode.json").read_text(encoding="utf-8"))
    client = make_client(cfg, dry_run=not args.apply, force_mock=not args.use_sheets)
    result = apply(client, do_apply=args.apply, allow_media_posts=bool(autonomous.get("allow_media_posts", False)), strict_trusted_media_review=args.require_trusted_media_review)
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 2 if args.apply and result.get("status") != "APPLIED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
