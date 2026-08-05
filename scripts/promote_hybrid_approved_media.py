#!/usr/bin/env python3
"""Promote only explicitly selected Hybrid-approved media queue rows."""
from __future__ import annotations

import argparse
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

MEDIA_MODES = {
    "direct_reference_media",
    "saved_direct_reference_media",
    "approved_source_clip",
    "saved_approved_source_clip",
    "system_owned_media",
}
ALLOWED_RIGHTS = {"owned", "licensed", "approved_creator_clip"}


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def is_media(row: dict[str, Any]) -> bool:
    mode = str(row.get("generation_mode") or row.get("content_type") or "").lower()
    return mode in MEDIA_MODES or truthy(row.get("media_required"))


def build_plan(
    client: SheetsClient,
    account_id: str,
    slot_id: str,
    queue_ids: set[str] | None = None,
) -> dict[str, Any]:
    requested = set(queue_ids or set())
    rows = [dict(row) for row in read_records_safely(client, "queue")]
    selected: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for row in rows:
        queue_id = str(row.get("queue_id", ""))
        if requested and queue_id not in requested:
            continue
        if str(row.get("account_id") or row.get("target_account_id") or "") != account_id:
            continue
        if str(row.get("slot_id", "")) != slot_id:
            continue
        if str(row.get("status", "")).upper() != "WAITING_REVIEW":
            continue
        if truthy(row.get("excluded_from_activation")) or truthy(row.get("repost_prohibited")):
            continue
        reasons: list[str] = []
        if not is_media(row):
            reasons.append("not_media")
        if not requires_hybrid_ai_gate(row):
            reasons.append("hybrid_gate_not_required")
        gate_ok, gate_reason = hybrid_ai_gate_passed(row, build_source_context(client, row))
        if not gate_ok:
            reasons.append(f"hybrid_ai_gate_{gate_reason}")
        if str(row.get("rights_status", "")).lower() not in ALLOWED_RIGHTS:
            reasons.append("rights_not_allowed")
        if str(row.get("permission_status", "")).lower() not in {"approved", "not_required"}:
            reasons.append("permission_not_approved")
        if str(row.get("validator_status", "")).upper() != "PASS":
            reasons.append("validator_not_pass")
        if str(row.get("internal_leak_status", "")).upper() != "PASS":
            reasons.append("internal_leak_not_pass")
        if str(row.get("account_fit_status", "")).upper() != "PASS":
            reasons.append("account_fit_not_pass")
        media_url = str(
            row.get("media_url")
            or row.get("storage_url")
            or row.get("media_urls_json")
            or ""
        ).strip()
        if not media_url:
            reasons.append("media_url_missing")
        if reasons:
            rejected.append({"queue_id": queue_id, "reasons": ",".join(reasons)})
            continue
        selected.append(row)
    selected.sort(
        key=lambda row: (
            int(str(row.get("priority", "999") or "999")),
            str(row.get("created_at", "")),
            str(row.get("queue_id", "")),
        )
    )
    chosen = selected[:1]
    return {
        "status": "PLAN_READY",
        "account_id": account_id,
        "slot_id": slot_id,
        "requested_queue_ids": sorted(requested),
        "selected_queue_ids": [str(row.get("queue_id", "")) for row in chosen],
        "updated_queue_ids": [],
        "rejected": rejected[:20],
        "would_post": False,
    }


def apply(client: SheetsClient, result: dict[str, Any]) -> dict[str, Any]:
    updated: list[str] = []
    for queue_id in result["selected_queue_ids"]:
        client.update_queue_item(
            queue_id,
            status="READY",
            auto_publish="false",
            blocked_reason="",
            error="",
            auto_ready_by="promote_hybrid_approved_media.py",
            auto_ready_reason="hybrid_ai_and_persisted_media_validators_passed",
        )
        updated.append(queue_id)
    return {
        **result,
        "status": "APPLIED",
        "updated_queue_ids": updated,
        "updated_count": len(updated),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"])
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--queue-id", action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-promote", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if args.apply == args.dry_run:
        raise RuntimeError("specify exactly one of --apply or --dry-run")
    if args.apply and not args.confirm_promote:
        raise RuntimeError("--apply requires --confirm-promote")
    if not args.use_sheets:
        raise RuntimeError("--use-sheets is required")
    if not args.queue_id:
        raise RuntimeError("at least one --queue-id is required")
    cfg = get_config()
    client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
    result = build_plan(client, args.account_id, args.slot_id, set(args.queue_id))
    if args.apply:
        result = apply(client, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
