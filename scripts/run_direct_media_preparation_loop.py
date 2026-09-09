#!/usr/bin/env python3
"""Prepare one Direct media candidate with bounded post-Hybrid failover."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from accounts.managed_accounts import account_allows_autonomous_ready, account_choices  # noqa: E402


def extract_last_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    found: list[tuple[int, int, dict[str, Any]]] = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            found.append((index, index + end, value))
    found.sort(key=lambda item: (item[1], -item[0]))
    return found[-1][2] if found else {}


def run(command: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    return completed


def execute(
    account_id: str,
    slot_id: str,
    max_attempts: int,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = run,
    prefer_existing: bool = False,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    autonomous = account_allows_autonomous_ready(account_id)
    for number in range(1, max_attempts + 1):
        ingest_command = [
            sys.executable,
            "scripts/ingest_direct_reference_media_reliable.py",
            "--account-id", account_id,
            "--max-assets", "10",
            "--apply", "--confirm-ingest",
        ]
        ingest = subprocess.CompletedProcess(ingest_command, 0, '{"status":"EXISTING_ASSETS_FIRST"}', "")
        if not prefer_existing:
            ingest = runner(ingest_command)
        prepare_env = os.environ.copy()
        prepare_env.pop("REQUIRE_PREPARED", None)
        prepare_command = [
            sys.executable,
            "scripts/run_direct_reference_media_pipeline_batched.py",
            "--account-id", account_id,
            "--slot-id", slot_id,
            "--prepare-only", "--apply", "--confirm-direct-media", "--use-sheets",
        ]
        prepared = runner(prepare_command, env=prepare_env)
        initial = extract_last_object(prepared.stdout)
        if prefer_existing and not (initial.get("queue_id") or initial.get("generated_queue_id")):
            ingest = runner(ingest_command)
            prepared = runner(prepare_command, env=prepare_env)
        ingest_payload = extract_last_object(ingest.stdout)
        prepare_payload = extract_last_object(prepared.stdout)
        queue_id = str(prepare_payload.get("queue_id") or prepare_payload.get("generated_queue_id") or "")
        attempt = {
            "attempt": number,
            "ingest_status": str(ingest_payload.get("status", "")),
            "prepare_status": str(prepare_payload.get("status", "")),
            "queue_id": queue_id,
            "blocked_reasons": list(prepare_payload.get("blocked_reasons", []))[:10],
            "ingest_returncode": ingest.returncode,
            "prepare_returncode": prepared.returncode,
        }
        if not queue_id:
            attempts.append(attempt)
            continue

        gate = runner([
            sys.executable,
            "scripts/run_hybrid_ai_queue_gate.py",
            "--account-id", account_id,
            "--slot-id", slot_id,
            "--queue-id", queue_id,
            "--max-candidates", "1",
            "--apply", "--use-sheets",
        ])
        gate_payload = extract_last_object(gate.stdout)
        exact = next(
            (row for row in gate_payload.get("results", []) if str(row.get("queue_id", "")) == queue_id),
            {},
        )
        gate_status = str(exact.get("status", ""))
        attempt["hybrid_status"] = gate_status or "NO_RESULT"
        attempt["blocked_reasons"] = list(exact.get("blocked_reasons", []))[:10]
        attempts.append(attempt)
        if gate_status != "PASS":
            continue
        if not autonomous:
            return {
                "status": "WAITING_REVIEW",
                "account_id": account_id,
                "slot_id": slot_id,
                "selected_queue_id": queue_id,
                "attempts": attempts,
                "would_post": False,
            }
        promotion = runner([
            sys.executable,
            "scripts/promote_hybrid_approved_media.py",
            "--account-id", account_id,
            "--slot-id", slot_id,
            "--queue-id", queue_id,
            "--autonomous-low-risk",
            "--apply", "--confirm-promote", "--use-sheets",
        ])
        promotion_payload = extract_last_object(promotion.stdout)
        if queue_id in promotion_payload.get("updated_queue_ids", []):
            return {
                "status": "READY",
                "account_id": account_id,
                "slot_id": slot_id,
                "selected_queue_id": queue_id,
                "attempts": attempts,
                "would_post": False,
            }
        attempt["promotion_status"] = str(promotion_payload.get("status", ""))
    return {
        "status": "NO_ELIGIBLE_MEDIA",
        "account_id": account_id,
        "slot_id": slot_id,
        "selected_queue_id": "",
        "attempts": attempts,
        "would_post": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True, choices=account_choices(production_only=True))
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-preparation-loop", action="store_true")
    parser.add_argument("--minimum-ready", type=int, default=3)
    args = parser.parse_args()
    if not args.apply or not args.confirm_preparation_loop:
        raise RuntimeError("production preparation loop requires apply and explicit confirmation")
    if not 1 <= args.max_attempts <= 10:
        raise RuntimeError("max_attempts_must_be_between_1_and_10")
    if not 1 <= args.minimum_ready <= 7:
        raise RuntimeError("minimum_ready_must_be_between_1_and_7")
    from config_loader import get_config
    from sheets_client import SheetsClient
    from sheets_record_reader import enable_readonly_record_cache, read_records_safely
    from process_threads_queue import process_one
    from production_inventory import eligible_ready, has_media

    def inventory():
        cfg = get_config()
        client = SheetsClient(cfg["sheet_id"], cfg["sa_dict"], dry_run=False)
        enable_readonly_record_cache(client)
        return {str(r["media_asset_id"]) for r in read_records_safely(client, "queue")
            if eligible_ready(r, args.account_id) and has_media(r) and r.get("media_asset_id")
            and r.get("generation_mode") == "direct_reference_media"
            and process_one(client, r, dry_run=True, confirm_real_post=False).get("status") == "DRY_RUN"}

    initial = inventory()
    result = {"status": "READY", "ready_media_count": len(initial), "would_post": False}
    for _ in range(max(0, args.minimum_ready - len(initial))):
        result = execute(args.account_id, args.slot_id, args.max_attempts, prefer_existing=True)
        current = inventory()
        result["ready_media_count"] = len(current)
        if len(current) >= args.minimum_ready:
            break
        if result["status"] != "READY" or len(current) <= len(initial):
            result["status"] = "MEDIA_INVENTORY_LOW"
            break
        initial = current
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ready_media_count", 0) >= args.minimum_ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
