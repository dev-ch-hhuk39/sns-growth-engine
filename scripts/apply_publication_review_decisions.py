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
from sheets_client import TAB_DEFINITIONS, _col_letter, make_client  # noqa: E402


def build_decisions(review_rows: list[dict], queue_rows: list[dict], *, allow_media_posts: bool) -> list[tuple[dict, dict, str, dict[str, str]]]:
    queues = {text(row.get("queue_id")): row for row in queue_rows}
    result = []
    for review in review_rows:
        queue = queues.get(text(review.get("queue_id")))
        if not queue:
            continue
        outcome, fields = decision_for_row(review, queue, allow_media_posts=allow_media_posts)
        if outcome != "SKIP":
            result.append((review, queue, outcome, fields))
    return result


def apply(client, *, do_apply: bool, allow_media_posts: bool) -> dict:
    if not hasattr(client, "_ensure_tab") or not hasattr(client, "_ws"):
        return {"status": "MOCK_PLAN", "decision_count": 0}
    client._ensure_tab("queue", TAB_DEFINITIONS["queue"])
    if do_apply:
        client._ensure_tab("publication_review", TAB_DEFINITIONS["publication_review"])
    queue_rows = [dict(row) for row in client._ws("queue").get_all_records()]
    review_rows = [dict(row) for row in client._ws("publication_review").get_all_records()]
    plans = build_decisions(review_rows, queue_rows, allow_media_posts=allow_media_posts)
    report = {"status": "APPLIED" if do_apply else "PLAN_ONLY", "decision_count": len(plans), "outcomes": [outcome for _, _, outcome, _ in plans]}
    if not do_apply:
        return report
    review_ws = client._ws("publication_review")
    review_headers = review_ws.row_values(1)
    review_by_queue = {text(row.get("queue_id")): index for index, row in enumerate(review_rows, start=2)}
    review_updates = []
    updated_queue_ids = []
    for review, queue, outcome, fields in plans:
        if fields:
            client.update_queue_item(text(queue.get("queue_id")), **fields)
            updated_queue_ids.append(text(queue.get("queue_id")))
        row_no = review_by_queue.get(text(review.get("queue_id")))
        if row_no:
            for field, value in {"decision_result": outcome, "decision_applied_at": now_iso(), "review_status": "APPROVED" if outcome == "READY" else outcome}.items():
                if field in review_headers:
                    review_updates.append({"range": f"{_col_letter(review_headers.index(field) + 1)}{row_no}", "values": [[value]]})
    if review_updates:
        review_ws.batch_update(review_updates, value_input_option="USER_ENTERED")
    saved = {text(row.get("queue_id")): row for row in client._ws("queue").get_all_records()}
    report["queue_read_after_write"] = all(queue_id in saved for queue_id in updated_queue_ids)
    report["updated_queue_ids"] = updated_queue_ids
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-review-decisions", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.apply and not args.confirm_review_decisions:
        raise SystemExit("BLOCKED: --apply requires --confirm-review-decisions")
    cfg = get_config()
    autonomous = __import__("json").loads((ROOT / "config" / "autonomous_mode.json").read_text(encoding="utf-8"))
    client = make_client(cfg, dry_run=not args.apply, force_mock=not args.use_sheets)
    result = apply(client, do_apply=args.apply, allow_media_posts=bool(autonomous.get("allow_media_posts", False)))
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
