#!/usr/bin/env python3
"""Review WAITING_REVIEW candidates without READY transition or posting."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]

from config_loader import get_config  # noqa: E402
from gemini_hybrid_client import GeminiHybridClient  # noqa: E402
from hybrid_ai_gate import HybridAiGate, hybrid_ai_gate_current, merge_gate_audit  # noqa: E402
from hybrid_ai_policy import requires_hybrid_ai_gate  # noqa: E402
from hybrid_ai_source_context import build_source_context  # noqa: E402
from sheets_client import SheetsClient  # noqa: E402
from sheets_record_reader import read_records_safely  # noqa: E402

JST = ZoneInfo("Asia/Tokyo")
EXECUTION_MAX = int(os.environ.get("HYBRID_AI_EXECUTION_MAX_REQUESTS", "20"))
DAILY_MAX = int(os.environ.get("HYBRID_AI_DAILY_MAX_REQUESTS", "40"))
MONTHLY_MAX = int(os.environ.get("HYBRID_AI_MONTHLY_MAX_REQUESTS", "1000"))


def now_jst() -> datetime:
    return datetime.now(JST)


def now_iso() -> str:
    return now_jst().isoformat()


def canonical_hash(rows: list[dict[str, Any]]) -> str:
    raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def records(client: SheetsClient, logical: str) -> list[dict[str, Any]]:
    return [dict(row) for row in read_records_safely(client, logical)]


def parse_timestamp(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(JST)


class SheetsBudgetLedger:
    """Persistent global budget based on verified Sheets reservation logs."""

    def __init__(self, client: SheetsClient, account_id: str) -> None:
        self.client = client
        self.account_id = account_id
        self.execution_used = 0

    def reserve(self, metadata: dict[str, Any]) -> None:
        if self.execution_used + 1 > EXECUTION_MAX:
            raise RuntimeError("hybrid_ai_execution_limit_exceeded")
        now = now_jst()
        logs = [dict(row) for row in read_records_safely(self.client, "logs")]
        reservations = [
            row
            for row in logs
            if str(row.get("operation", "")) == "hybrid_ai_request_reserved"
            and str(row.get("status", "")).upper() == "OK"
        ]
        daily_used = 0
        monthly_used = 0
        for row in reservations:
            timestamp = parse_timestamp(row.get("timestamp") or row.get("created_at"))
            if timestamp is None:
                continue
            if timestamp.strftime("%Y-%m") == now.strftime("%Y-%m"):
                monthly_used += 1
            if timestamp.strftime("%Y-%m-%d") == now.strftime("%Y-%m-%d"):
                daily_used += 1
        if daily_used + 1 > DAILY_MAX:
            raise RuntimeError("hybrid_ai_daily_limit_exceeded")
        if monthly_used + 1 > MONTHLY_MAX:
            raise RuntimeError("hybrid_ai_monthly_limit_exceeded")
        details = json.dumps(metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.client.log(
            operation="hybrid_ai_request_reserved",
            status="OK",
            message=f"Gemini request reserved: {metadata.get('operation', '')}",
            account_id=self.account_id,
            details=details,
            level="INFO",
        )
        self.execution_used += 1


def candidate_rows(
    client: SheetsClient,
    account_id: str,
    max_candidates: int,
    slot_id: str = "",
) -> tuple[list[tuple[dict[str, Any], dict[str, Any]]], list[dict[str, str]]]:
    rows = [
        dict(row)
        for row in client.get_queue_items(account_id=account_id, platform="threads", status="WAITING_REVIEW")
    ]
    eligible = [
        row
        for row in rows
        if requires_hybrid_ai_gate(row)
        and (not slot_id or str(row.get("slot_id", "")) == slot_id)
        and str(row.get("excluded_from_activation", "")).lower() not in {"true", "1", "yes"}
        and str(row.get("repost_prohibited", "")).lower() not in {"true", "1", "yes"}
    ]
    if slot_id:
        eligible.sort(key=lambda row: (str(row.get("created_at", "")), str(row.get("queue_id", ""))), reverse=True)
        eligible = eligible[:max_candidates]
    else:
        eligible.sort(
            key=lambda row: (
                int(str(row.get("priority", "999") or "999")),
                str(row.get("created_at", "")),
                str(row.get("queue_id", "")),
            )
        )
    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    skipped_current: list[dict[str, str]] = []
    for row in eligible:
        source_context = build_source_context(client, row)
        current, current_status = hybrid_ai_gate_current(row, source_context)
        if current:
            skipped_current.append({"queue_id": str(row.get("queue_id", "")), "gate_status": current_status})
            continue
        selected.append((row, source_context))
        if len(selected) >= max_candidates:
            break
    return selected, skipped_current


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"])
    parser.add_argument("--max-candidates", type=int, default=2)
    parser.add_argument("--slot-id", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if args.apply == args.dry_run:
        raise RuntimeError("specify exactly one of --apply or --dry-run")
    if not 1 <= args.max_candidates <= 2:
        raise RuntimeError("max_candidates_must_be_between_1_and_2")
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        print(json.dumps({
            "status": "FAILED_MISSING_GEMINI_API_KEY",
            "account_id": args.account_id,
            "slot_id": args.slot_id,
            "no_ready_transition": True,
            "no_post": True,
        }, ensure_ascii=False))
        return 2
    if not args.use_sheets:
        raise RuntimeError("--use-sheets is required for production queue review")

    cfg = get_config()
    client = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=False)
    ledger = SheetsBudgetLedger(client, args.account_id)
    gemini = GeminiHybridClient(reserve_request=ledger.reserve)
    gate = HybridAiGate(gemini)
    selected, skipped_current = candidate_rows(client, args.account_id, args.max_candidates, args.slot_id)
    posted_before = records(client, "posted_results")
    statuses_before = {
        str(queue.get("queue_id", "")): str(queue.get("status", ""))
        for queue, _source_context in selected
    }
    results: list[dict[str, Any]] = []
    runtime_errors: list[dict[str, str]] = []

    for queue, source_context in selected:
        queue_id = str(queue.get("queue_id", ""))
        try:
            result = gate.evaluate(queue, source_context)
        except Exception as exc:
            error_code = type(exc).__name__
            runtime_errors.append({"queue_id": queue_id, "error": error_code})
            if args.apply:
                client.update_queue_item(
                    queue_id,
                    error="HYBRID_AI_GATE_RUNTIME_ERROR",
                    blocked_reason="HYBRID_AI_GATE_RUNTIME_ERROR",
                    updated_at=now_iso(),
                )
                client.log(
                    operation="hybrid_ai_gate_runtime_error",
                    status="FAILED",
                    message=f"Hybrid AI gate runtime error: {queue_id}",
                    account_id=args.account_id,
                    details=json.dumps({"queue_id": queue_id, "error_type": error_code}, ensure_ascii=False, sort_keys=True),
                    level="ERROR",
                )
            continue

        audit_json = merge_gate_audit(queue.get("generation_policy_json", ""), result)
        blocked_reason = ",".join(result.blocked_reasons)[:500]
        fields = {
            "public_post_text": result.public_post_text,
            "generation_policy_json": audit_json,
            "generated_by": "hybrid_ai_gate_v2",
            "validator_status": "PASS" if result.status == "PASS" else "BLOCKED",
            "text_policy_status": "PASS" if result.status == "PASS" else "BLOCKED",
            "account_fit_status": "PASS" if result.status == "PASS" else "BLOCKED",
            "internal_leak_status": "PASS" if result.status == "PASS" else "BLOCKED",
            "blocked_reason": "" if result.status == "PASS" else blocked_reason,
            "error": "" if result.status == "PASS" else blocked_reason,
            "internal_analysis": json.dumps(
                {
                    "hybrid_ai_gate": result.status,
                    "route": result.route,
                    "blocked_reasons": result.blocked_reasons,
                    "actual_requests": result.actual_requests,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "caption_provider": os.environ.get("GEMINI_GENERATOR_MODEL", "gemini-3.5-flash"),
            "caption_provider_version": "hybrid_ai_gate_v2",
            "updated_at": now_iso(),
        }
        if args.apply:
            client.update_queue_item(queue_id, **fields)
            client.log(
                operation="hybrid_ai_gate_evaluated",
                status="OK" if result.status == "PASS" else "BLOCKED",
                message=f"Hybrid AI gate {result.status}: {queue_id}",
                account_id=args.account_id,
                details=json.dumps(
                    {"queue_id": queue_id, "route": result.route, "blocked_reasons": result.blocked_reasons},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                level="INFO",
            )
        results.append({"queue_id": queue_id, **result.audit()})

    if args.apply:
        selected_after = {str(row.get("queue_id", "")): row for row in records(client, "queue")}
        for queue_id, status_before in statuses_before.items():
            if str(selected_after[queue_id].get("status", "")) != status_before:
                raise RuntimeError(f"queue_status_changed_by_hybrid_gate:{queue_id}")
        posted_after = records(client, "posted_results")
        if canonical_hash(posted_after) != canonical_hash(posted_before):
            raise RuntimeError("posted_results_changed_by_hybrid_gate")

    output = {
        "status": "PASS" if not runtime_errors else "PARTIAL_ERROR",
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "account_id": args.account_id,
        "slot_id": args.slot_id,
        "candidate_count": len(selected),
        "skipped_current_count": len(skipped_current),
        "skipped_current": skipped_current,
        "actual_request_count": gemini.actual_request_count,
        "execution_max_requests": EXECUTION_MAX,
        "results": results,
        "runtime_errors": runtime_errors,
        "no_ready_transition": True,
        "no_post": True,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not runtime_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
