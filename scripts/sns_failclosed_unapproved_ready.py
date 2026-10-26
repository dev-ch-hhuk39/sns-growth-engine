#!/usr/bin/env python3
"""Exact one-row, fail-closed READY rollback if approval audit is missing.

Not a READY approver. Never creates missing approvals or posts content.
No mass update, no sheet setup, no replay after unknown mutation outcome.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime/current")
if not (ROOT / "src" / "sheets_client.py").is_file():
    ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from config_loader import get_config  # noqa: E402
from sheets_client import make_client  # noqa: E402

EXPECTED = "b16c42f9e757"
ACCOUNT = "night_scout"
MODE = "original_text"
BLOCKED_REASON = "READY_APPROVAL_LOG_MISSING_REVIEW_REQUIRED"


def approval_log_ids(logs: list[dict]) -> set[str]:
    result = set()
    for row in logs:
        if str(row.get("operation") or "").strip() != "queue_approved":
            continue
        blob = str(row.get("details") or "") + " " + str(row.get("message") or "")
        result.update(match.strip() for match in re.findall(r"queue_id=([^\s]+)", blob))
    return result


def plan(queues: list[dict], logs: list[dict], posted: list[dict]) -> dict:
    if not isinstance(queues, list) or not isinstance(logs, list) or not isinstance(posted, list):
        raise ValueError("INVALID_SHEETS_SNAPSHOT")
    approved = approval_log_ids(logs)
    matches = [
        row for row in queues
        if str(row.get("account_id") or "") == ACCOUNT
        and str(row.get("generation_mode") or "").lower() == MODE
        and str(row.get("status") or "").upper() == "READY"
        and hashlib.sha256(str(row.get("queue_id") or "").encode()).hexdigest()[:12] == EXPECTED
    ]
    if len(matches) != 1:
        raise ValueError("EXPECTED_READY_EXACT_ROW_MISSING_OR_AMBIGUOUS")
    row = matches[0]
    qid = str(row.get("queue_id") or "")
    if not qid or sum(str(other.get("queue_id") or "") == qid for other in queues) != 1:
        raise ValueError("QUEUE_ID_NOT_UNIQUE")
    if qid in approved:
        raise ValueError("APPROVAL_LOG_EXISTS_NO_ROLLBACK")
    if any(str(item.get("queue_id") or "") == qid for item in posted):
        raise ValueError("POST_RESULT_EXISTS_NO_ROLLBACK")
    if str(row.get("platform") or "").lower() != "threads":
        raise ValueError("NOT_THREADS")
    if str(row.get("auto_ready_by") or "").strip() != "auto_approve_queue.py":
        raise ValueError("UNEXPECTED_APPROVAL_OWNER")
    if any(str(row.get(k) or "").strip() for k in
           ("media_asset_id", "media_url", "source_video_id", "external_post_id", "posted_at")):
        raise ValueError("ROW_MAY_CONTAIN_MEDIA_OR_EXTERNAL_EVIDENCE")
    if str(row.get("media_required") or "").lower() in ("true", "yes", "1"):
        raise ValueError("MEDIA_READY_NOT_WITHIN_SCOPE")
    if str(row.get("human_approved") or "").lower() == "true":
        raise ValueError("EXPLICIT_HUMAN_APPROVAL_PRESENT")
    return {"queue_id": qid, "account_id": ACCOUNT, "id_hash": EXPECTED, "status_before": "READY",
            "status_after": "WAITING_REVIEW", "media": False}


def execute(client: object, *, apply: bool) -> dict:
    queues = [dict(row) for row in client._ws("queue").get_all_records()]
    logs = [dict(row) for row in client._ws("logs").get_all_records()]
    posted = [dict(row) for row in client._ws("posted_results").get_all_records()]
    proposed = plan(queues, logs, posted)
    public = {k: v for k, v in proposed.items() if k != "queue_id"}
    if not apply:
        return {"status": "PLAN_ONLY", "target": public, "sheets_writes": 0, "posts": 0}
    if os.environ.get("BUFFERED_POSTING_ENABLED", "").lower() != "false":
        raise ValueError("POSTING_DISABLE_PRECONDITION_MISSING")
    # The official queue writer re-checks exact identity and read-after-write.
    client.update_queue_item(
        proposed["queue_id"], status="WAITING_REVIEW", auto_publish="false",
        blocked_reason=BLOCKED_REASON,
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    current = client.get_queue_item(proposed["queue_id"])
    if not current or str(current.get("status") or "").upper() != "WAITING_REVIEW":
        raise RuntimeError("WRITE_RESULT_REQUIRES_MANUAL_RECONCILIATION")
    if str(current.get("auto_publish") or "").lower() != "false":
        raise RuntimeError("AUTO_PUBLISH_FLAG_REQUIRES_MANUAL_RECONCILIATION")
    if str(current.get("blocked_reason") or "") != BLOCKED_REASON:
        raise RuntimeError("BLOCKED_REASON_REQUIRES_MANUAL_RECONCILIATION")
    return {"status": "REVIEW_REQUIRED_SAFELY", "target": public,
            "sheets_writes": 1, "posts": 0, "approval_logs_created": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-failclosed", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.confirm_failclosed:
        print('SNS_READY_FAILCLOSED_REPAIR={"status":"BLOCKED_CONFIRMATION_MISSING","posts":0}')
        return 2
    try:
        cfg = get_config()
        client = make_client(cfg, dry_run=not args.apply, force_mock=False)
        result = execute(client, apply=args.apply)
        print("SNS_READY_FAILCLOSED_REPAIR=" + json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print('SNS_READY_FAILCLOSED_REPAIR={"status":"BLOCKED_OR_OUTCOME_UNKNOWN","posts":0,"must_not_retry_without_independent_readback":true}')
        return 1


if __name__ == "__main__":
    sys.exit(main())
