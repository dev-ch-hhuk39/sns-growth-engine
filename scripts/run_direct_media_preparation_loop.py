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

from accounts.managed_accounts import account_choices, managed_account  # noqa: E402


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
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    autonomous = str(managed_account(account_id).get("review_policy", "")) == "autonomous_low_risk"
    for number in range(1, max_attempts + 1):
        ingest = runner([
            sys.executable,
            "scripts/ingest_direct_reference_media_reliable.py",
            "--account-id", account_id,
            "--max-assets", "1",
            "--apply", "--confirm-ingest",
        ])
        ingest_payload = extract_last_object(ingest.stdout)
        prepare_env = os.environ.copy()
        prepare_env.pop("REQUIRE_PREPARED", None)
        prepared = runner([
            sys.executable,
            "scripts/run_direct_reference_media_pipeline_batched.py",
            "--account-id", account_id,
            "--slot-id", slot_id,
            "--prepare-only", "--apply", "--confirm-direct-media", "--use-sheets",
        ], env=prepare_env)
        prepare_payload = extract_last_object(prepared.stdout)
        queue_id = str(prepare_payload.get("queue_id") or prepare_payload.get("generated_queue_id") or "")
        attempt = {
            "attempt": number,
            "ingest_status": str(ingest_payload.get("status", "")),
            "prepare_status": str(prepare_payload.get("status", "")),
            "queue_id": queue_id,
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
    args = parser.parse_args()
    if not args.apply or not args.confirm_preparation_loop:
        raise RuntimeError("production preparation loop requires apply and explicit confirmation")
    if not 1 <= args.max_attempts <= 10:
        raise RuntimeError("max_attempts_must_be_between_1_and_10")
    result = execute(args.account_id, args.slot_id, args.max_attempts)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"READY", "WAITING_REVIEW", "NO_ELIGIBLE_MEDIA"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
