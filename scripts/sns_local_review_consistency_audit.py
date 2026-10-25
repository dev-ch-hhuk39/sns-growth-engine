#!/usr/bin/env python3
"""Read-only Sheets review integrity monitor when the writer is quarantined.

This script NEVER writes to Sheets, clears a quarantine latch, posts content,
approves a draft, or calls a paid LLM. Reports only aggregated counts.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime/current")
if not (ROOT / "src" / "sheets_client.py").is_file():
    ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from config_loader import get_config  # noqa: E402
from sheets_client import make_client  # noqa: E402
from publication_review_board import is_reviewable, review_row, text  # noqa: E402
from review_board_integrity import (  # noqa: E402
    index_review_rows, require_review_account_match,
)

IGNORE_SYNC_FIELDS = frozenset({
    "updated_at", "last_sync_at", "created_at", "review_status",
    "review_decision", "reviewer_note", "decision_applied_at", "decision_result",
})


def audit_rows(queue_rows: list[dict], review_rows: list[dict]) -> dict:
    queues = index_review_rows(queue_rows, source="QUEUE")
    reviews = index_review_rows(review_rows, source="REVIEW")
    require_review_account_match(reviews, queues)
    drift = missing = feedback_ok = feedback_unverified = pending = 0
    reviewables = 0
    for key, q in queues.items():
        if not is_reviewable(q):
            continue
        reviewables += 1
        old = reviews.get(key)
        if old is None:
            missing += 1
            continue
        desired = review_row(q, old)
        if any(text(old.get(field)) != text(value) for field, value in desired.items()
               if field not in IGNORE_SYNC_FIELDS):
            drift += 1
        decision = text(old.get("review_decision")).upper()
        if decision not in {"OK", "NG", "HOLD"}:
            continue
        is_applied = text(old.get("decision_result")).upper() == "FEEDBACK_RECORDED"
        if is_applied:
            confirmed = (
                text(q.get("status")).upper() in {"POSTED", "READY"}
                and text(q.get("human_review_status")).upper() == decision
                and text(q.get("human_review_note")) == text(old.get("reviewer_note"))
                and bool(text(q.get("reviewed_at")))
                and bool(text(old.get("decision_applied_at")))
            )
            if confirmed:
                feedback_ok += 1
            else:
                feedback_unverified += 1
        else:
            pending += 1
    status = "CONSISTENT" if not (missing or drift or feedback_unverified) else "REQUIRES_RECONCILIATION"
    return {
        "status": status,
        "queue_rows": len(queues),
        "review_rows": len(reviews),
        "reviewable": reviewables,
        "projection_drift": drift,
        "missing_review_rows": missing,
        "verified_feedback": feedback_ok,
        "unverified_feedback": feedback_unverified,
        "pending_explicit_decisions": pending,
        "sheets_writes": 0, "social_posts": 0, "paid_ai_calls": 0,
    }


def main() -> int:
    try:
        client = make_client(get_config(), dry_run=True, force_mock=False)
        q = [dict(x) for x in client._ws("queue").get_all_records()]
        r = [dict(x) for x in client._ws("publication_review").get_all_records()]
        result = audit_rows(q, r)
        print("SNS_REVIEW_READONLY_AUDIT=" + json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["status"] == "CONSISTENT" else 2
    except Exception:
        print('SNS_REVIEW_READONLY_AUDIT={"status":"UNVERIFIED","sheets_writes":0,"social_posts":0}')
        return 1


if __name__ == "__main__":
    sys.exit(main())
