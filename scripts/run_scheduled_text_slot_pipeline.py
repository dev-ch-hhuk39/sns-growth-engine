#!/usr/bin/env python3
"""Generate, Hybrid-review, promote, and conditionally publish one scheduled text slot."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from scheduled_execution_guard import append_job_summary, scheduled_window_decision  # noqa: E402


def extract_json_objects(text: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    values: list[tuple[int, dict[str, Any]]] = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append((index + end, value))
    values.sort(key=lambda item: item[0])
    return [value for _end, value in values]


def run_stage(name: str, command: list[str], env: dict[str, str]) -> tuple[int, dict[str, Any]]:
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
    payloads = extract_json_objects(completed.stdout)
    payload = payloads[-1] if payloads else {}
    print(json.dumps({"stage": name, "returncode": completed.returncode}, ensure_ascii=False))
    return completed.returncode, payload


def no_post(reason: str, *, account_id: str, slot_id: str, queue_id: str = "", details: Any = None) -> int:
    payload = {
        "status": "NO_POST",
        "reason": reason,
        "account_id": account_id,
        "slot_id": slot_id,
        "queue_id": queue_id,
        "details": details or {},
        "would_post": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    append_job_summary("Scheduled text result: NO_POST", payload)
    return 2


def generated_queue_ids(payload: dict[str, Any]) -> list[str]:
    """Return only queue IDs created/refreshed by this generation run."""
    for result in payload.get("results", []):
        if "generate_threads_ideas_from_references.py" not in str(result.get("cmd", "")):
            continue
        generation = result.get("payload") or {}
        values = generation.get("effective_queue_ids", generation.get("queue_ids", []))
        return list(dict.fromkeys(str(value) for value in values if str(value)))
    return []


def generation_failure_reason(payload: dict[str, Any]) -> str:
    for result in payload.get("results", []):
        if "generate_threads_ideas_from_references.py" not in str(result.get("cmd", "")):
            continue
        stderr = str(result.get("stderr_tail", ""))
        if "HTTP 429" in stderr or "RESOURCE_EXHAUSTED" in stderr:
            return "GEMINI_RATE_LIMITED"
        generation = result.get("payload") or {}
        reason = str(generation.get("reason", "")).strip()
        if reason:
            return reason.upper()
    return "NO_GENERATED_SLOT_CANDIDATE"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-id", required=True, choices=["night_scout", "liver_manager"])
    parser.add_argument("--slot-id", required=True)
    parser.add_argument("--use-sheets", action="store_true")
    args = parser.parse_args()
    if not args.use_sheets:
        raise RuntimeError("--use-sheets is required")

    base_env = dict(os.environ)
    safe_env = {
        **base_env,
        "PUBLISH_ENABLED": "false",
        "ALLOW_REAL_THREADS_POST": "false",
        "ALLOW_REAL_X_POST": "false",
        "ALLOW_MEDIA_POSTS": "false",
        "ALLOW_REAL_THREADS_VIDEO_POST": "false",
        "ALLOW_VIDEO_DOWNLOAD": "false",
        "ALLOW_VIDEO_CUT": "false",
        "ALLOW_CLOUDINARY_UPLOAD": "false",
        "ALLOW_TRANSCRIPTION_API": "false",
    }

    window = scheduled_window_decision(args.slot_id)
    append_job_summary("Scheduled execution window", window)

    generation = [
        sys.executable,
        "scripts/run_autonomous_loop.py",
        "--apply",
        "--confirm-autonomous",
        "--stop-before-post",
        "--account-id",
        args.account_id,
        "--slot-id",
        args.slot_id,
    ]
    rc, generation_payload = run_stage("generate_waiting_review", generation, safe_env)
    if rc != 0:
        return no_post(
            "CANDIDATE_GENERATION_FAILED",
            account_id=args.account_id,
            slot_id=args.slot_id,
            details=generation_payload,
        )

    queue_ids = generated_queue_ids(generation_payload)
    if len(queue_ids) != 1:
        return no_post(
            "NO_AI_APPROVED_CANDIDATE",
            account_id=args.account_id,
            slot_id=args.slot_id,
            details={
                "generation_reason": generation_failure_reason(generation_payload),
                "generated_queue_ids": queue_ids,
            },
        )
    generated_queue_id = queue_ids[0]

    ready_output = Path(f"/tmp/hybrid-ready-text-{args.account_id}-{args.slot_id}.json")
    ready_command = [
        sys.executable,
        "scripts/run_hybrid_ready_pipeline.py",
        "--account-id",
        args.account_id,
        "--slot-id",
        args.slot_id,
        "--queue-id",
        generated_queue_id,
        "--max-candidates",
        "1",
        "--approval-mode",
        "text",
        "--apply",
        "--use-sheets",
        "--json-output",
        str(ready_output),
    ]
    rc, ready_payload = run_stage("hybrid_review_and_auto_ready", ready_command, safe_env)
    if ready_output.exists():
        ready_payload = json.loads(ready_output.read_text(encoding="utf-8"))
    if rc != 0:
        ready_status = str(ready_payload.get("status", ""))
        ready_reason = str(ready_payload.get("reason", ""))
        reason = (
            "QUALITY_BLOCKED"
            if ready_status == "NO_READY_CANDIDATE" and ready_reason == "no_hybrid_pass_candidate_for_exact_slot"
            else "NO_READY_CANDIDATE"
            if ready_status == "NO_READY_CANDIDATE"
            else "HYBRID_REVIEW_FAILED"
        )
        return no_post(
            reason,
            account_id=args.account_id,
            slot_id=args.slot_id,
            details=ready_payload,
        )

    queue_id = str(ready_payload.get("selected_queue_id", "")).strip()
    if not queue_id or queue_id != generated_queue_id:
        return no_post(
            "NO_AI_APPROVED_SLOT_CANDIDATE",
            account_id=args.account_id,
            slot_id=args.slot_id,
            details=ready_payload,
        )

    activation = [sys.executable, "scripts/scheduled_publish_activation_gate.py", "--use-sheets"]
    rc, activation_payload = run_stage("runtime_activation_gate", activation, safe_env)
    append_job_summary("Runtime activation gate", activation_payload)
    if rc != 0:
        return no_post(
            "RUNTIME_ACTIVATION_GATE_BLOCKED",
            account_id=args.account_id,
            slot_id=args.slot_id,
            queue_id=queue_id,
            details=activation_payload,
        )

    if window.get("status") != "PASS":
        return no_post(
            "SCHEDULED_RUN_OUT_OF_WINDOW",
            account_id=args.account_id,
            slot_id=args.slot_id,
            queue_id=queue_id,
            details=window,
        )

    publish_env = {
        **base_env,
        "PUBLISH_ENABLED": "true",
        "ALLOW_REAL_THREADS_POST": "true",
        "ALLOW_REAL_X_POST": "false",
        "ALLOW_MEDIA_POSTS": "false",
        "ALLOW_REAL_THREADS_VIDEO_POST": "false",
        "ALLOW_VIDEO_DOWNLOAD": "false",
        "ALLOW_VIDEO_CUT": "false",
        "ALLOW_CLOUDINARY_UPLOAD": "false",
        "ALLOW_TRANSCRIPTION_API": "false",
    }
    publish = [
        sys.executable,
        "scripts/process_threads_queue.py",
        "--account-id",
        args.account_id,
        "--queue-id",
        queue_id,
        "--max-posts",
        "1",
        "--confirm-real-post",
    ]
    rc, publish_payload = run_stage("publish_exact_queue", publish, publish_env)
    result = {
        "status": "POSTED" if rc == 0 else "FAILED",
        "account_id": args.account_id,
        "slot_id": args.slot_id,
        "selected_queue_id": queue_id,
        "publish_payload": publish_payload,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    append_job_summary("Scheduled text result", result)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
