#!/usr/bin/env python3
"""Archive every pre-activation READY/WAITING_REVIEW row before fresh schedules start."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from config_loader import get_config  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from sheets_record_reader import read_records_safely  # noqa: E402

TARGET_ACCOUNTS = {"night_scout", "liver_manager"}
TARGET_STATUSES = {"READY", "WAITING_REVIEW"}
ARCHIVE_REASON = "pre_activation_queue_archived_for_fresh_schedule"


def canonical_hash(rows: list[dict[str, Any]]) -> str:
    raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_plan(rows: list[dict[str, Any]]) -> dict[str, Any]:
    targets = []
    for row in rows:
        account_id = str(row.get("account_id") or row.get("target_account_id") or "")
        status = str(row.get("status", "")).upper()
        if account_id not in TARGET_ACCOUNTS or status not in TARGET_STATUSES:
            continue
        if str(row.get("excluded_from_activation", "")).lower() in {"true", "1", "yes"}:
            continue
        targets.append({
            "queue_id": str(row.get("queue_id", "")),
            "account_id": account_id,
            "prior_status": status,
            "slot_id": str(row.get("slot_id", "")),
            "generation_mode": str(row.get("generation_mode", "")),
            "public_post_preview": str(row.get("public_post_text", ""))[:120],
        })
    targets.sort(key=lambda row: (row["account_id"], row["prior_status"], row["queue_id"]))
    return {
        "status": "PLAN_READY",
        "archive_count": len(targets),
        "by_account": {
            account: sum(1 for row in targets if row["account_id"] == account)
            for account in sorted(TARGET_ACCOUNTS)
        },
        "targets": targets,
        "would_post": False,
    }


def apply_plan(client: SheetsClient, result: dict[str, Any]) -> dict[str, Any]:
    posted_before = [dict(row) for row in read_records_safely(client, "posted_results")]
    posted_hash_before = canonical_hash(posted_before)
    for row in result["targets"]:
        client.update_queue_item(
            row["queue_id"],
            status="WAITING_REVIEW",
            auto_publish="false",
            excluded_from_activation="true",
            excluded_from_metrics_baseline="true",
            repost_prohibited="true",
            blocked_reason=ARCHIVE_REASON,
            superseded_reason="fresh_scheduled_pipeline_required",
            error=ARCHIVE_REASON,
        )
    posted_after = [dict(row) for row in read_records_safely(client, "posted_results")]
    posted_hash_after = canonical_hash(posted_after)
    if posted_hash_after != posted_hash_before:
        raise RuntimeError("posted_results_changed_during_pre_activation_archive")
    queue_after = [dict(row) for row in read_records_safely(client, "queue")]
    remaining = [
        row for row in queue_after
        if str(row.get("account_id") or row.get("target_account_id") or "") in TARGET_ACCOUNTS
        and str(row.get("status", "")).upper() in TARGET_STATUSES
        and str(row.get("excluded_from_activation", "")).lower() not in {"true", "1", "yes"}
    ]
    if remaining:
        raise RuntimeError(f"pre_activation_archive_incomplete:{len(remaining)}")
    return {
        **result,
        "status": "APPLIED",
        "updated_count": len(result["targets"]),
        "remaining_unarchived_count": 0,
        "posted_results_hash_before": posted_hash_before,
        "posted_results_hash_after": posted_hash_after,
        "no_post": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-archive", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--json-output", default="")
    args = parser.parse_args()
    if args.apply == args.dry_run:
        raise RuntimeError("specify exactly one of --apply or --dry-run")
    if args.apply and not args.confirm_archive:
        raise RuntimeError("--apply requires --confirm-archive")
    if not args.use_sheets:
        raise RuntimeError("--use-sheets is required")
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    rows = [dict(row) for row in read_records_safely(client, "queue")]
    result = build_plan(rows)
    if args.apply:
        result = apply_plan(client, result)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.json_output:
        Path(args.json_output).write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
