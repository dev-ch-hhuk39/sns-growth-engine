#!/usr/bin/env python3
"""Move unreviewed READY slot inventory back to WAITING_REVIEW before Hybrid AI."""
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
from hybrid_ai_gate import hybrid_ai_gate_passed  # noqa: E402
from hybrid_ai_policy import requires_hybrid_ai_gate  # noqa: E402
from hybrid_ai_source_context import build_source_context  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from sheets_record_reader import read_records_safely  # noqa: E402


def canonical_hash(rows: list[dict[str, Any]]) -> str:
    raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def plan(client: SheetsClient, account_id: str, slot_id: str) -> dict[str, Any]:
    rows = [dict(row) for row in read_records_safely(client, "queue")]
    changes: list[dict[str, str]] = []
    for row in rows:
        if str(row.get("account_id") or row.get("target_account_id") or "") != account_id:
            continue
        if str(row.get("slot_id", "")) != slot_id:
            continue
        if str(row.get("status", "")).upper() != "READY":
            continue
        if not requires_hybrid_ai_gate(row):
            continue
        gate_ok, _reason = hybrid_ai_gate_passed(row, build_source_context(client, row))
        if gate_ok:
            continue
        changes.append({
            "queue_id": str(row.get("queue_id", "")),
            "from_status": "READY",
            "to_status": "WAITING_REVIEW",
        })
    return {
        "status": "PLAN_READY",
        "account_id": account_id,
        "slot_id": slot_id,
        "change_count": len(changes),
        "changes": changes,
        "would_post": False,
    }


def apply(client: SheetsClient, result: dict[str, Any]) -> dict[str, Any]:
    posted_before = [dict(row) for row in read_records_safely(client, "posted_results")]
    for change in result["changes"]:
        client.update_queue_item(
            change["queue_id"],
            status="WAITING_REVIEW",
            auto_publish="false",
            blocked_reason="hybrid_ai_gate_pending",
            error="hybrid_ai_gate_pending",
            auto_ready_by="",
            auto_ready_reason="",
            auto_ready_score="",
            auto_ready_at="",
        )
    posted_after = [dict(row) for row in read_records_safely(client, "posted_results")]
    if canonical_hash(posted_after) != canonical_hash(posted_before):
        raise RuntimeError("posted_results_changed_during_slot_normalization")
    return {**result, "status": "APPLIED", "updated_count": len(result["changes"]), "no_post": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"])
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-normalize", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if args.apply == args.dry_run:
        raise RuntimeError("specify exactly one of --apply or --dry-run")
    if args.apply and not args.confirm_normalize:
        raise RuntimeError("--apply requires --confirm-normalize")
    if not args.use_sheets:
        raise RuntimeError("--use-sheets is required")
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    result = plan(client, args.account_id, args.slot_id)
    if args.apply:
        result = apply(client, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
