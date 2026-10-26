#!/usr/bin/env python3
"""One-time independently verified review projection repair; no publish/approval.

Runs only with existing writer quarantine marker and disabled posting.
Uses patched pure projection with native Sheets sync readback/write-once safety.
DO NOT schedule this tool or use it to clear the original writer quarantine.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime/current")
if not (ROOT / "src" / "sheets_client.py").is_file():
    ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from config_loader import get_config  # noqa: E402
from sheets_client import make_client  # noqa: E402
import sync_publication_review as native  # noqa: E402
from review_board_integrity import (  # noqa: E402
    index_review_rows, require_review_account_match,
)
from publication_review_board import text  # noqa: E402

LATCH = Path("/opt/github-runners/sns-growth-engine/.buffered-runtime/shared/review-board-state/manual_reconciliation_required")
MAX_NEW = 100
MAX_CHANGES = 25
REVIEWER_FIELDS = ("review_decision", "reviewer_note", "decision_applied_at", "decision_result")


def patched_review_module():
    path = Path(__file__).resolve().parent / "publication_review_board.py"
    if path.is_symlink() or not path.is_file():
        raise ValueError("PATCHED_PURE_HELPER_MISSING")
    spec = importlib.util.spec_from_file_location("sns_oneoff_verified_review_projection", path)
    if not spec or not spec.loader:
        raise ValueError("PATCHED_PROJECTION_UNLOADABLE")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validated_plan(queues: list[dict], reviews: list[dict], helper) -> dict:
    qi = index_review_rows(queues, source="QUEUE")
    ri = index_review_rows(reviews, source="REVIEW")
    require_review_account_match(ri, qi)
    projections = [
        helper.review_row(q, ri.get(qid)) for qid, q in qi.items()
        if helper.is_reviewable(q)
    ]
    if len(projections) > 5000:
        raise ValueError("REVIEW_INVENTORY_OUT_OF_BOUNDS")
    missing = [p for p in projections if p["queue_id"] not in ri]
    drift = []
    feedback_count = 0
    for row in projections:
        qid = row["queue_id"]
        old = ri.get(qid)
        if old is None:
            continue
        for field in REVIEWER_FIELDS:
            if text(old.get(field)) != text(row.get(field)):
                raise ValueError("REVIEWER_CELL_PROJECTION_MUTATION")
        differences = [
            field for field in row
            if field not in REVIEWER_FIELDS
            and field not in {"updated_at", "last_sync_at", "created_at"}
            and text(old.get(field)) != text(row.get(field))
        ]
        if differences:
            if text(old.get("decision_result")).upper() == "FEEDBACK_RECORDED":
                if differences != ["review_status"] or row["review_status"] != "FEEDBACK_RECORDED":
                    raise ValueError("APPLIED_FEEDBACK_MATERIAL_CHANGE")
            drift.append((qid, differences))
    for qid, old in ri.items():
        if text(old.get("decision_result")).upper() != "FEEDBACK_RECORDED":
            continue
        if qid not in qi:
            raise ValueError("ACKNOWLEDGED_FEEDBACK_QUEUE_MISSING")
        q = qi[qid]
        if not (
            text(q.get("status")).upper() in {"READY", "POSTED"}
            and text(q.get("human_review_status")).upper() == text(old.get("review_decision")).upper()
            and text(q.get("human_review_note")) == text(old.get("reviewer_note"))
            and bool(text(old.get("decision_applied_at")))
            and bool(text(q.get("reviewed_at")))
        ):
            raise ValueError("APPLIED_FEEDBACK_NOT_INDEPENDENTLY_CONFIRMED")
        feedback_count += 1
    if not (0 < len(missing) <= MAX_NEW):
        raise ValueError("MISSING_REVIEW_BATCH_NOT_WITHIN_BOUNDS")
    if len(drift) > MAX_CHANGES:
        raise ValueError("DRIFT_BATCH_TOO_LARGE")
    return {
        "missing": len(missing), "drift_rows": len(drift),
        "verified_feedback": feedback_count,
        "projected": len(projections),
        "posts": 0, "queue_writes": 0, "reviewer_decision_writes": 0,
    }


def execute(*, apply: bool) -> dict:
    if os.environ.get("BUFFERED_POSTING_ENABLED") != "false":
        raise ValueError("POSTING_OFF_REQUIRED")
    if not LATCH.exists() or LATCH.is_symlink():
        raise ValueError("EXISTING_WRITER_QUARANTINE_REQUIRED")
    helper = patched_review_module()
    client = make_client(get_config(), dry_run=not apply, force_mock=False)
    queues = [dict(x) for x in client._ws("queue").get_all_records()]
    reviews = [dict(x) for x in client._ws("publication_review").get_all_records()]
    proof = validated_plan(queues, reviews, helper)
    if not apply:
        return {"status": "PLAN_ONLY", **proof, "sheets_writes": 0}
    # Existing native synchronizer is write-once and verifies the changed
    # projection readback, preserving reviewer cells. Only the pure
    # idempotency-corrected function is substituted. No direct queue writer.
    native.review_row = helper.review_row
    native.is_reviewable = helper.is_reviewable
    result = native.sync(client, apply=True)
    if result.get("status") != "APPLIED" or result.get("read_after_write") is not True:
        raise ValueError("REVIEW_WRITE_NOT_VERIFIED")
    if result.get("appended_count") != proof["missing"]:
        raise ValueError("REVIEW_APPENDED_COUNT_MISMATCH_REQUIRES_MANUAL_RECHECK")
    after = [dict(x) for x in client._ws("publication_review").get_all_records()]
    after_index = index_review_rows(after, source="REVIEW")
    before_index = index_review_rows(reviews, source="REVIEW")
    for qid, old in before_index.items():
        fresh = after_index.get(qid)
        if not fresh:
            raise ValueError("EXISTING_REVIEW_REMOVED_REQUIRES_MANUAL_RECHECK")
        if any(text(old.get(field)) != text(fresh.get(field)) for field in REVIEWER_FIELDS):
            raise ValueError("HUMAN_REVIEW_CELL_CHANGED_REQUIRES_MANUAL_RECHECK")
    post_proof = validated_plan_allow_empty(queues, after, helper)
    if post_proof["missing"] or post_proof["drift_rows"]:
        raise ValueError("POST_SYNC_PROJECTION_DRIFT_REQUIRES_MANUAL_RECHECK")
    return {"status": "RECONCILED_READBACK_VERIFIED",
            **proof, "appended_rows": result.get("appended_count", 0),
            "updated_cells": result.get("updated_count", 0),
            "sheets_writes": 2 if result.get("updated_count", 0) else 1,
            "read_after_write": True, "original_writer_latch_preserved": True}


def validated_plan_allow_empty(queues: list[dict], reviews: list[dict], helper) -> dict:
    # A no-op batch after successful reconciliation is expected.
    # Still verify reviewer-cell consistency and every acknowledged feedback.
    try:
        return validated_plan(queues, reviews, helper)
    except ValueError as exc:
        if str(exc) != "MISSING_REVIEW_BATCH_NOT_WITHIN_BOUNDS":
            raise
        qi = index_review_rows(queues, source="QUEUE")
        ri = index_review_rows(reviews, source="REVIEW")
        require_review_account_match(ri, qi)
        for qid, q in qi.items():
            if helper.is_reviewable(q):
                row = ri.get(qid)
                if not row:
                    raise ValueError("POST_SYNC_MISSING_ROW")
                expected = helper.review_row(q, row)
                if any(text(row.get(k)) != text(v) for k, v in expected.items()
                       if k not in REVIEWER_FIELDS and k not in {"updated_at", "last_sync_at", "created_at"}):
                    raise ValueError("POST_SYNC_REVIEW_DRIFT")
        return {"missing": 0, "drift_rows": 0}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-oneoff", action="store_true")
    args = parser.parse_args()
    if args.apply and not args.confirm_oneoff:
        print('SNS_REVIEW_ONEOFF={"status":"BLOCKED_CONFIRMATION_REQUIRED","posts":0}')
        return 2
    try:
        report = execute(apply=args.apply)
        print("SNS_REVIEW_ONEOFF=" + json.dumps(report, sort_keys=True))
        return 0
    except Exception:
        print('SNS_REVIEW_ONEOFF={"status":"BLOCKED_OR_UNKNOWN_MANUAL_RECONCILIATION","posts":0,"must_not_auto_retry":true}')
        return 1


if __name__ == "__main__":
    sys.exit(main())
