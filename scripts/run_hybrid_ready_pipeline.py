#!/usr/bin/env python3
"""Review the newest exact slot candidate and promote only that queue ID."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts")]

from accounts.managed_accounts import account_choices  # noqa: E402
from scheduled_execution_guard import append_job_summary  # noqa: E402


def extract_json_objects(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    candidates: list[tuple[int, int, dict[str, Any]]] = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            candidates.append((index, index + end, value))
    candidates.sort(key=lambda item: (item[1], -item[0]))
    return [item[2] for item in candidates]


def gate_command(
    account_id: str,
    slot_id: str,
    max_candidates: int,
    apply: bool,
    *,
    approval_mode: str = "text",
    queue_id: str = "",
) -> list[str]:
    command = [
        sys.executable,
        "scripts/run_hybrid_ai_queue_gate.py",
        "--account-id",
        account_id,
        "--slot-id",
        slot_id,
        "--max-candidates",
        str(max_candidates),
        "--apply" if apply else "--dry-run",
        "--use-sheets",
    ]
    if approval_mode == "media":
        command.append("--require-human-review")
    if queue_id:
        command.extend(["--queue-id", queue_id])
    return command


def approval_command(account_id: str, slot_id: str, queue_id: str, *, apply: bool, approval_mode: str) -> list[str]:
    if approval_mode == "text":
        return [
            sys.executable,
            "scripts/auto_approve_queue.py",
            "--account-id",
            account_id,
            "--slot-id",
            slot_id,
            "--queue-id",
            queue_id,
            "--max-ready",
            "1",
            "--use-sheets",
            "--skip-setup",
            *(["--apply", "--confirm-auto-ready"] if apply else ["--dry-run"]),
        ]
    return [
        sys.executable,
        "scripts/promote_hybrid_approved_media.py",
        "--account-id",
        account_id,
        "--slot-id",
        slot_id,
        "--queue-id",
        queue_id,
        "--use-sheets",
        *(["--apply", "--confirm-promote"] if apply else ["--dry-run"]),
    ]


def command_plan(
    account_id: str,
    slot_id: str,
    max_candidates: int,
    *,
    apply: bool,
    approval_mode: str = "text",
    queue_id: str = "",
) -> list[list[str]]:
    commands = [gate_command(
        account_id,
        slot_id,
        max_candidates,
        apply,
        approval_mode=approval_mode,
        queue_id=queue_id,
    )]
    if queue_id:
        commands.append(approval_command(account_id, slot_id, queue_id, apply=apply, approval_mode=approval_mode))
    return commands


def run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, check=False, text=True, capture_output=True)


def run_stage(stage_name: str, command: list[str], runner: Callable[[list[str]], subprocess.CompletedProcess[str]]) -> tuple[dict[str, Any], bool]:
    completed = runner(command)
    if completed.stdout:
        print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="" if completed.stderr.endswith("\n") else "\n")
    payloads = extract_json_objects(completed.stdout)
    payload = payloads[-1] if payloads else {}
    return ({"stage": stage_name, "returncode": completed.returncode, "payload": payload}, completed.returncode == 0)


def reviewed_pass_queue_ids(payload: dict[str, Any]) -> list[str]:
    queue_ids: list[str] = []
    for row in payload.get("results", []):
        if str(row.get("status", "")).upper() == "PASS":
            queue_ids.append(str(row.get("queue_id", "")))
    for row in payload.get("skipped_current", []):
        if str(row.get("gate_status", "")).upper() == "PASS":
            queue_ids.append(str(row.get("queue_id", "")))
    return list(dict.fromkeys(item for item in queue_ids if item))


def execute(
    account_id: str,
    slot_id: str,
    max_candidates: int,
    *,
    apply: bool,
    approval_mode: str = "text",
    queue_id: str = "",
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] = run_command,
) -> dict[str, Any]:
    stages: list[dict[str, Any]] = []
    gate_stage, gate_ok = run_stage(
        "hybrid_gate",
        gate_command(
            account_id,
            slot_id,
            max_candidates,
            apply,
            approval_mode=approval_mode,
            queue_id=queue_id,
        ),
        runner,
    )
    stages.append(gate_stage)
    if not gate_ok:
        return {
            "status": "FAILED",
            "failed_stage": "hybrid_gate",
            "account_id": account_id,
            "slot_id": slot_id,
            "selected_queue_id": "",
            "updated_queue_ids": [],
            "stages": stages,
            "would_post": False,
        }

    reviewed_ids = reviewed_pass_queue_ids(gate_stage["payload"])
    if queue_id:
        reviewed_ids = [item for item in reviewed_ids if item == queue_id]
    if not reviewed_ids:
        return {
            "status": "NO_READY_CANDIDATE",
            "reason": "no_hybrid_pass_candidate_for_exact_slot",
            "account_id": account_id,
            "slot_id": slot_id,
            "selected_queue_id": "",
            "updated_queue_ids": [],
            "stages": stages,
            "would_post": False,
        }
    if len(reviewed_ids) != 1:
        return {
            "status": "FAILED",
            "failed_stage": "exact_queue_selection",
            "reason": "slot_gate_returned_multiple_pass_candidates",
            "account_id": account_id,
            "slot_id": slot_id,
            "selected_queue_id": "",
            "updated_queue_ids": [],
            "stages": stages,
            "would_post": False,
        }

    selected_queue_id = reviewed_ids[0]
    stage_name = "auto_ready" if approval_mode == "text" else "media_promote"
    approval_stage, approval_ok = run_stage(
        stage_name,
        approval_command(account_id, slot_id, selected_queue_id, apply=apply, approval_mode=approval_mode),
        runner,
    )
    stages.append(approval_stage)
    if not approval_ok:
        return {
            "status": "FAILED",
            "failed_stage": stage_name,
            "account_id": account_id,
            "slot_id": slot_id,
            "selected_queue_id": selected_queue_id,
            "updated_queue_ids": [],
            "stages": stages,
            "would_post": False,
        }

    updated = [str(item) for item in approval_stage["payload"].get("updated_queue_ids", []) if str(item)]
    status = "READY" if selected_queue_id in updated else "NO_READY_CANDIDATE"
    return {
        "status": status,
        "reason": "" if status == "READY" else "exact_candidate_not_promoted_ready",
        "account_id": account_id,
        "slot_id": slot_id,
        "selected_queue_id": selected_queue_id if status == "READY" else "",
        "updated_queue_ids": updated,
        "stages": stages,
        "would_post": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True, choices=account_choices())
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--queue-id", default="")
    parser.add_argument("--max-candidates", type=int, default=1)
    parser.add_argument("--approval-mode", choices=["text", "media"], default="text")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--use-sheets", action="store_true")
    parser.add_argument("--json-output", default="")
    args = parser.parse_args()
    if args.apply == args.dry_run:
        raise RuntimeError("specify exactly one of --apply or --dry-run")
    if not args.use_sheets:
        raise RuntimeError("--use-sheets is required")
    if args.max_candidates != 1:
        raise RuntimeError("scheduled slot pipeline requires max_candidates=1")
    result = execute(
        args.account_id,
        args.slot_id,
        args.max_candidates,
        apply=args.apply,
        approval_mode=args.approval_mode,
        queue_id=args.queue_id,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    append_job_summary("Hybrid exact-slot result", result)
    if args.json_output:
        Path(args.json_output).write_text(rendered + "\n", encoding="utf-8")
    return 0 if result["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
