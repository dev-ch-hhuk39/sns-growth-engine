#!/usr/bin/env python3
"""Review and regenerate WAITING_REVIEW queue candidates without READY or posting."""
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
from hybrid_ai_gate import HybridAiGate, merge_gate_audit  # noqa: E402
from hybrid_ai_policy import requires_hybrid_ai_gate  # noqa: E402
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
    try:
        return [dict(row) for row in read_records_safely(client, logical)]
    except Exception:
        return []


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
    def __init__(self, client: SheetsClient, account_id: str) -> None:
        self.client = client
        self.account_id = account_id
        self.execution_used = 0

    def reserve(self, metadata: dict[str, Any]) -> None:
        if self.execution_used + 1 > EXECUTION_MAX:
            raise RuntimeError("hybrid_ai_execution_limit_exceeded")
        now = now_jst()
        logs = records(self.client, "logs")
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


def _lookup(rows: list[dict[str, Any]], keys: tuple[str, ...], value: str) -> dict[str, Any]:
    if not value:
        return {}
    for row in rows:
        if any(str(row.get(key, "")) == value for key in keys):
            return row
    return {}


def build_source_context(client: SheetsClient, queue: dict[str, Any]) -> dict[str, Any]:
    source_post_id = str(queue.get("source_post_id", ""))
    source_video_id = str(queue.get("source_video_id", ""))
    clip_candidate_id = str(queue.get("clip_candidate_id", ""))
    source_id = str(queue.get("source_id", ""))
    source_post = _lookup(records(client, "source_posts"), ("source_post_id", "post_id"), source_post_id)
    clip = _lookup(records(client, "video_clip_candidates"), ("clip_candidate_id", "clip_id"), clip_candidate_id)
    source_video = _lookup(records(client, "source_videos"), ("source_video_id", "video_id"), source_video_id)
    source_rows: list[dict[str, Any]] = []
    for logical in ("video_sources", "source_accounts", "reference_sources"):
        source_rows.extend(records(client, logical))
    source = _lookup(source_rows, ("source_id", "account_id"), source_id)
    claim_support = str(queue.get("claim_support_json", ""))
    return {
        "source_post_id": source_post_id,
        "source_video_id": source_video_id,
        "clip_candidate_id": clip_candidate_id,
        "source_id": source_id,
        "original_post_text": source_post.get("original_post_text", ""),
        "transcript_excerpt": clip.get("transcript_excerpt", ""),
        "transcript": source_video.get("transcript", ""),
        "description": source_video.get("description", "") or source.get("description", ""),
        "source_text": claim_support,
        "use_policy": source.get("use_policy", ""),
        "usage_scope": source.get("usage_scope", ""),
        "reuse_policy": source.get("reuse_policy", ""),
        "source_target_account_id": source.get("target_account_id", ""),
        "classifier_model": os.environ.get("GEMINI_CLASSIFIER_MODEL", "gemini-2.5-flash-lite"),
        "generator_model": os.environ.get("GEMINI_GENERATOR_MODEL", "gemini-2.5-flash"),
        "review_model": os.environ.get("GEMINI_REVIEW_MODEL", "gemini-2.5-flash-lite"),
    }


def candidate_rows(client: SheetsClient, account_id: str, max_candidates: int) -> list[dict[str, Any]]:
    rows = [
        dict(row)
        for row in client.get_queue_items(account_id=account_id, platform="threads", status="WAITING_REVIEW")
    ]
    eligible = [
        row
        for row in rows
        if requires_hybrid_ai_gate(row)
        and str(row.get("excluded_from_activation", "")).lower() not in {"true", "1", "yes"}
        and str(row.get("repost_prohibited", "")).lower() not in {"true", "1", "yes"}
    ]
    eligible.sort(key=lambda row: (int(str(row.get("priority", "999") or "999")), str(row.get("created_at", "")), str(row.get("queue_id", ""))))
    return eligible[:max_candidates]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"])
    parser.add_argument("--max-candidates", type=int, default=3)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if args.apply == args.dry_run:
        raise RuntimeError("specify exactly one of --apply or --dry-run")
    if not 1 <= args.max_candidates <= 3:
        raise RuntimeError("max_candidates_must_be_between_1_and_3")
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        print(json.dumps({"status": "SKIPPED_NO_GEMINI_API_KEY", "account_id": args.account_id}, ensure_ascii=False))
        return 0
    if not args.use_sheets:
        raise RuntimeError("--use-sheets is required for production queue review")

    cfg = get_config()
    client = SheetsClient(sheet_id=cfg["sheet_id"], sa_dict=cfg["sa_dict"], dry_run=False)
    ledger = SheetsBudgetLedger(client, args.account_id)
    gemini = GeminiHybridClient(reserve_request=ledger.reserve)
    gate = HybridAiGate(gemini)
    selected = candidate_rows(client, args.account_id, args.max_candidates)
    posted_before = records(client, "posted_results")
    statuses_before = {str(row.get("queue_id", "")): str(row.get("status", "")) for row in selected}
    results: list[dict[str, Any]] = []

    for queue in selected:
        source_context = build_source_context(client, queue)
        result = gate.evaluate(queue, source_context)
        audit_json = merge_gate_audit(queue.get("generation_policy_json", ""), result)
        blocked_reason = ",".join(result.blocked_reasons)[:500]
        fields = {
            "public_post_text": result.public_post_text,
            "generation_policy_json": audit_json,
            "generated_by": "hybrid_ai_gate_v1",
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
            "caption_provider": os.environ.get("GEMINI_GENERATOR_MODEL", "gemini-2.5-flash"),
            "caption_provider_version": "hybrid_ai_gate_v1",
            "updated_at": now_iso(),
        }
        if args.apply:
            client.update_queue_item(str(queue["queue_id"]), **fields)
            client.log(
                operation="hybrid_ai_gate_evaluated",
                status="OK" if result.status == "PASS" else "BLOCKED",
                message=f"Hybrid AI gate {result.status}: {queue['queue_id']}",
                account_id=args.account_id,
                details=json.dumps({"queue_id": queue["queue_id"], "route": result.route, "blocked_reasons": result.blocked_reasons}, ensure_ascii=False, sort_keys=True),
                level="INFO",
            )
        results.append({"queue_id": queue["queue_id"], **result.audit()})

    if args.apply:
        selected_after = {str(row.get("queue_id", "")): row for row in records(client, "queue")}
        for queue_id, status_before in statuses_before.items():
            if str(selected_after[queue_id].get("status", "")) != status_before:
                raise RuntimeError(f"queue_status_changed_by_hybrid_gate:{queue_id}")
        posted_after = records(client, "posted_results")
        if canonical_hash(posted_after) != canonical_hash(posted_before):
            raise RuntimeError("posted_results_changed_by_hybrid_gate")

    output = {
        "status": "PASS",
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "account_id": args.account_id,
        "candidate_count": len(selected),
        "actual_request_count": gemini.actual_request_count,
        "execution_max_requests": EXECUTION_MAX,
        "results": results,
        "no_ready_transition": True,
        "no_post": True,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
