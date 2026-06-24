#!/usr/bin/env python3
"""Process one or more Threads queue rows safely.

Default mode is dry-run. Real posting requires all of:
- --confirm-real-post
- PUBLISH_ENABLED=true
- ALLOW_REAL_THREADS_POST=true

This worker never posts X, never posts beauty_account, and never retries
immediately after a failure.
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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from config_loader import get_config  # noqa: E402
from publishers.threads_publisher import ThreadsPublisher  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402

ELIGIBLE_STATUSES = {"WAITING_REVIEW", "PLANNED"}
FINAL_OR_LOCKED_STATUSES = {
    "POSTED",
    "PROCESSING",
    "FAILED",
    "POSTED_SAVE_FAILED",
    "DUPLICATE_BLOCKED",
}
BEAUTY_BLOCKED = {"beauty_account"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def is_true(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes"}


def get_ws(client: SheetsClient, logical: str):
    return client._ws(logical)


def records(client: SheetsClient, logical: str) -> list[dict[str, Any]]:
    return [dict(r) for r in get_ws(client, logical).get_all_records()]


def row_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(r.get(key, "")): r for r in rows if str(r.get(key, ""))}


def append_row(client: SheetsClient, logical: str, row: dict[str, Any]) -> None:
    ws = get_ws(client, logical)
    headers = ws.row_values(1)
    ws.append_row([str(row.get(h, "")) for h in headers], value_input_option="USER_ENTERED")


def update_row(client: SheetsClient, logical: str, key: str, key_value: str, fields: dict[str, Any]) -> bool:
    ws = get_ws(client, logical)
    headers = ws.row_values(1)
    if key not in headers:
        raise KeyError(f"{logical}: missing key header {key}")
    cell = ws.find(key_value, in_column=headers.index(key) + 1)
    if cell is None:
        return False
    for field, value in fields.items():
        if field in headers:
            ws.update_cell(cell.row, headers.index(field) + 1, str(value))
    return True


def find_social_for_queue(client: SheetsClient, queue_row: dict[str, Any], social_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    draft_id = str(queue_row.get("draft_id", ""))
    for row in social_rows:
        if row.get("draft_id") == draft_id and str(row.get("platform", "")).lower() == "threads":
            return row
    return None


def find_draft_for_queue(queue_row: dict[str, Any], drafts_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    return drafts_by_id.get(str(queue_row.get("draft_id", "")))


def text_for_queue(queue_row: dict[str, Any], social: dict[str, Any] | None, draft: dict[str, Any] | None) -> str:
    if social and str(social.get("text", "")).strip():
        return str(social.get("text", "")).strip()
    if draft:
        for key in ("body_md", "content"):
            if str(draft.get(key, "")).strip():
                return str(draft.get(key, "")).strip()
    return ""


def duplicate_reason(
    *,
    queue_row: dict[str, Any],
    social: dict[str, Any] | None,
    text: str,
    posted_rows: list[dict[str, Any]],
) -> str:
    queue_id = str(queue_row.get("queue_id", ""))
    draft_id = str(queue_row.get("draft_id", ""))
    derivative_id = str(social.get("derivative_id", "")) if social else ""
    account_id = str(queue_row.get("account_id", ""))

    for posted in posted_rows:
        status = str(posted.get("status", "")).upper()
        platform = str(posted.get("platform", "")).lower()
        if platform and platform != "threads":
            continue
        if queue_id and str(posted.get("queue_id", "")) == queue_id:
            return f"queue_id already in posted_results: {queue_id}"
        if derivative_id and str(posted.get("derivative_id", "")) == derivative_id:
            return f"derivative_id already in posted_results: {derivative_id}"
        if draft_id and str(posted.get("draft_id", "")) == draft_id and status in {"POSTED", "RECOVERED"}:
            return f"draft_id already posted/recovered: {draft_id}"
        same_text = (
            status == "POSTED"
            and str(posted.get("account_id", "")) == account_id
            and str(posted.get("platform", "")).lower() == "threads"
            and str(posted.get("posted_text", "")).strip() == text.strip()
            and text.strip()
        )
        if same_text:
            return "same text/account/platform already POSTED"
    return ""


def select_candidates(client: SheetsClient, account_id: str | None, max_posts: int) -> list[dict[str, Any]]:
    rows = records(client, "queue")
    candidates: list[dict[str, Any]] = []
    for row in rows:
        row_account = str(row.get("account_id", ""))
        status = str(row.get("status", "")).upper()
        platform = str(row.get("platform", "")).lower()
        if row_account in BEAUTY_BLOCKED:
            continue
        if account_id and row_account != account_id:
            continue
        if platform != "threads":
            continue
        if status in FINAL_OR_LOCKED_STATUSES:
            continue
        if status not in ELIGIBLE_STATUSES:
            continue
        candidates.append(row)
    candidates.sort(key=lambda r: (int(str(r.get("priority", "999") or "999")), str(r.get("queue_id", ""))))
    return candidates[:max_posts]


def log_event(client: SheetsClient, account_id: str, status: str, message: str, details: dict[str, Any] | None = None) -> None:
    append_row(client, "logs", {
        "log_id": f"threads_queue_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
        "timestamp": now_iso(),
        "account_id": account_id,
        "operation": "process_threads_queue",
        "level": "INFO" if status in {"DRY_RUN", "POSTED", "SKIPPED"} else "ERROR",
        "status": status,
        "message": message,
        "details": json.dumps(details or {}, ensure_ascii=False),
    })


def save_pdca_initial(client: SheetsClient, queue_row: dict[str, Any], result_id: str) -> None:
    account_id = str(queue_row.get("account_id", ""))
    created_at = now_iso()
    append_row(client, "pdca_runs", {
        "run_id": f"pdca_threads_{result_id}",
        "account_id": account_id,
        "platform": "threads",
        "days": "0",
        "total_results": "1",
        "suggestion_count": "1",
        "next_jobs_count": "1",
        "best_content_type": "manual_pending",
        "best_er": "",
        "created_at": created_at,
        "notes": f"Initial PDCA placeholder after queue post result_id={result_id}; metrics pending.",
    })
    append_row(client, "prompt_improvement_suggestions", {
        "suggestion_id": f"sug_threads_{result_id}",
        "account_id": account_id,
        "created_at": created_at,
        "source": "process_threads_queue",
        "suggestion_type": "metrics_followup",
        "target_template": "",
        "current_behavior": "Threads post created; metrics not imported yet.",
        "suggested_change": "Import Threads metrics manually before changing prompts.",
        "reason": f"result_id={result_id}",
        "expected_impact": "Enable human-reviewed PDCA loop.",
        "priority": "medium",
        "status": "WAITING_REVIEW",
        "reviewed_by": "",
        "reviewed_at": "",
        "notes": "auto_apply=false; do not activate learning rule automatically.",
    })


def save_posted_result(
    client: SheetsClient,
    *,
    queue_row: dict[str, Any],
    social: dict[str, Any] | None,
    text: str,
    external_post_id: str,
    post_url: str,
) -> str:
    result_id = f"threads_{queue_row.get('queue_id')}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    permalink_note = " permalink_pending=true" if not post_url else ""
    append_row(client, "posted_results", {
        "result_id": result_id,
        "queue_id": queue_row.get("queue_id", ""),
        "draft_id": queue_row.get("draft_id", ""),
        "derivative_id": social.get("derivative_id", "") if social else "",
        "account_id": queue_row.get("account_id", ""),
        "platform": "threads",
        "external_post_id": external_post_id,
        "post_url": post_url,
        "posted_text": text,
        "posted_at": now_iso(),
        "status": "POSTED",
        "metrics_status": "PENDING",
        "real_post": "true",
        "media_used": "false",
        "source_queue_status": queue_row.get("status", ""),
        "save_source": "process_threads_queue",
        "created_by": "process_threads_queue",
        "measurement_window": "pending",
        "views": "0",
        "likes": "0",
        "comments": "0",
        "follows": "0",
        "profile_clicks": "0",
        "line_adds": "0",
        "manual_memo": f"Created by process_threads_queue. Metrics pending.{permalink_note}",
        "collected_at": now_iso(),
    })
    return result_id


def write_fallback(queue_row: dict[str, Any], social: dict[str, Any] | None, text: str, result: Any) -> Path:
    fallback_dir = ROOT / "output" / "posted_results_fallback"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    path = fallback_dir / f"{queue_row.get('queue_id', 'unknown')}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.json"
    payload = {
        "created_at": now_iso(),
        "queue": queue_row,
        "social": social or {},
        "posted_text": text,
        "external_post_id": getattr(result, "external_post_id", "") or "",
        "posted_url": getattr(result, "posted_url", "") or "",
        "message": getattr(result, "message", "") or "",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def process_one(client: SheetsClient, queue_row: dict[str, Any], *, dry_run: bool, confirm_real_post: bool) -> dict[str, Any]:
    account_id = str(queue_row.get("account_id", ""))
    queue_id = str(queue_row.get("queue_id", ""))

    social_rows = records(client, "social_derivatives")
    draft_rows = records(client, "drafts")
    posted_rows = records(client, "posted_results")
    social = find_social_for_queue(client, queue_row, social_rows)
    draft = find_draft_for_queue(queue_row, row_by_key(draft_rows, "draft_id"))
    text = text_for_queue(queue_row, social, draft)

    if account_id in BEAUTY_BLOCKED:
        return {"status": "BLOCKED", "reason": "beauty_account is blocked", "queue_id": queue_id}
    if str(queue_row.get("platform", "")).lower() != "threads":
        return {"status": "SKIPPED", "reason": "non-threads row ignored", "queue_id": queue_id}
    if not text:
        if not dry_run:
            update_row(client, "queue", "queue_id", queue_id, {"status": "FAILED", "error": "EMPTY_TEXT", "processed_at": now_iso()})
            log_event(client, account_id, "FAILED", "Queue text is empty", {"queue_id": queue_id})
        return {"status": "FAILED", "reason": "EMPTY_TEXT", "queue_id": queue_id}

    duplicate = duplicate_reason(queue_row=queue_row, social=social, text=text, posted_rows=posted_rows)
    if duplicate:
        if not dry_run:
            update_row(client, "queue", "queue_id", queue_id, {
                "status": "DUPLICATE_BLOCKED",
                "error": duplicate,
                "processed_at": now_iso(),
            })
            log_event(client, account_id, "DUPLICATE_BLOCKED", duplicate, {"queue_id": queue_id})
        return {"status": "DUPLICATE_BLOCKED", "reason": duplicate, "queue_id": queue_id}

    publisher = ThreadsPublisher()
    dry_result = publisher.publish(
        text,
        account={"account_id": account_id},
        derivative={"derivative_id": social.get("derivative_id", "") if social else "", "platform": "threads"},
        queue_item={"queue_id": queue_id, "platform": "threads"},
        dry_run=True,
    )
    if not dry_result.success:
        if not dry_run:
            update_row(client, "queue", "queue_id", queue_id, {"status": "FAILED", "error": dry_result.message, "processed_at": now_iso()})
            log_event(client, account_id, "FAILED", "Dry-run validation failed", {"queue_id": queue_id, "message": dry_result.message})
        return {"status": "FAILED", "reason": dry_result.message, "queue_id": queue_id}

    if dry_run:
        return {
            "status": "DRY_RUN",
            "read_only": True,
            "queue_id": queue_id,
            "account_id": account_id,
            "draft_id": queue_row.get("draft_id", ""),
            "derivative_id": social.get("derivative_id", "") if social else "",
            "text_length": len(text),
            "message": dry_result.message,
        }

    if not confirm_real_post:
        return {"status": "BLOCKED", "reason": "--confirm-real-post required", "queue_id": queue_id}
    if not is_true(os.environ.get("PUBLISH_ENABLED", "false")) or not is_true(os.environ.get("ALLOW_REAL_THREADS_POST", "false")):
        return {"status": "BLOCKED", "reason": "PUBLISH_ENABLED=true and ALLOW_REAL_THREADS_POST=true are required", "queue_id": queue_id}

    update_row(client, "queue", "queue_id", queue_id, {"status": "PROCESSING", "error": "", "processed_at": ""})
    log_event(client, account_id, "PROCESSING", "Threads queue row locked for processing", {"queue_id": queue_id})

    result = publisher.publish(
        text,
        account={"account_id": account_id},
        derivative={"derivative_id": social.get("derivative_id", "") if social else "", "platform": "threads"},
        queue_item={"queue_id": queue_id, "platform": "threads"},
        dry_run=False,
    )
    if not result.success:
        update_row(client, "queue", "queue_id", queue_id, {
            "status": "FAILED",
            "error": f"THREADS_API_FAILED: {result.message}",
            "processed_at": now_iso(),
        })
        log_event(client, account_id, "FAILED", "Threads post failed; no immediate retry", {"queue_id": queue_id, "message": result.message})
        return {"status": "FAILED", "reason": result.message, "queue_id": queue_id}

    try:
        result_id = save_posted_result(
            client,
            queue_row=queue_row,
            social=social,
            text=text,
            external_post_id=result.external_post_id or "",
            post_url=result.posted_url or "",
        )
        update_row(client, "queue", "queue_id", queue_id, {
            "status": "POSTED",
            "error": "",
            "processed_at": now_iso(),
        })
        save_pdca_initial(client, queue_row, result_id)
        log_event(client, account_id, "POSTED", "Threads post saved to posted_results", {"queue_id": queue_id, "result_id": result_id})
        return {
            "status": "POSTED",
            "queue_id": queue_id,
            "result_id": result_id,
            "external_post_id": result.external_post_id or "",
            "post_url": result.posted_url or "",
        }
    except Exception as exc:
        fallback = write_fallback(queue_row, social, text, result)
        update_row(client, "queue", "queue_id", queue_id, {
            "status": "POSTED_SAVE_FAILED",
            "error": f"posted_results save failed; fallback={fallback}",
            "processed_at": now_iso(),
        })
        log_event(client, account_id, "POSTED_SAVE_FAILED", "Posted but failed to save posted_results", {"queue_id": queue_id, "fallback": str(fallback), "error": str(exc)})
        return {"status": "POSTED_SAVE_FAILED", "queue_id": queue_id, "fallback": str(fallback)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Process Threads queue rows safely")
    parser.add_argument("--account-id", choices=["night_scout", "liver_manager", "beauty_account"], help="Target account")
    parser.add_argument("--dry-run", action="store_true", help="Validate only; no post or Sheets mutation")
    parser.add_argument("--confirm-real-post", action="store_true", help="Required for real post")
    parser.add_argument("--max-posts", type=int, default=1, help="Max posts to process. Default 1")
    args = parser.parse_args()

    if args.account_id == "beauty_account":
        print("[BLOCKED] beauty_account is draft_only and cannot be posted")
        return 1
    if args.max_posts < 1:
        print("[ERROR] --max-posts must be >= 1")
        return 1
    if args.max_posts > 1 and not args.confirm_real_post and not args.dry_run:
        print("[BLOCKED] real multi-post requires --confirm-real-post")
        return 1
    if args.max_posts > 2:
        print("[BLOCKED] --max-posts is capped at 2")
        return 1
    if not args.dry_run and not args.confirm_real_post:
        print("[BLOCKED] real post mode requires --confirm-real-post")
        return 1

    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    if args.dry_run:
        print("[READ_ONLY] --dry-run: setup_all/update/append/post/fallback are disabled")
    else:
        client.setup_all()

    candidates = select_candidates(client, args.account_id, args.max_posts)
    print(f"[process_threads_queue] candidates={len(candidates)} dry_run={args.dry_run} max_posts={args.max_posts}")
    if not candidates:
        print("[DONE] no eligible Threads queue rows")
        return 0

    results = []
    for queue_row in candidates:
        outcome = process_one(client, queue_row, dry_run=args.dry_run, confirm_real_post=args.confirm_real_post)
        results.append(outcome)
        print(json.dumps(outcome, ensure_ascii=False))

    bad = [r for r in results if r["status"] in {"FAILED", "POSTED_SAVE_FAILED"}]
    blocked = [r for r in results if r["status"] in {"BLOCKED"}]
    return 1 if bad or blocked else 0


if __name__ == "__main__":
    raise SystemExit(main())
