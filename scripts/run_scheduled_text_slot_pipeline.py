#!/usr/bin/env python3
"""Generate, Hybrid-review, promote, and publish one exact scheduled text slot."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


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
    rc, _payload = run_stage("generate_waiting_review", generation, safe_env)
    if rc != 0:
        return rc

    ready_output = Path("/tmp/hybrid-ready-text.json")
    ready_command = [
        sys.executable,
        "scripts/run_hybrid_ready_pipeline.py",
        "--account-id",
        args.account_id,
        "--slot-id",
        args.slot_id,
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
    if rc != 0:
        return rc
    if ready_output.exists():
        ready_payload = json.loads(ready_output.read_text(encoding="utf-8"))
    queue_id = str(ready_payload.get("selected_queue_id", "")).strip()
    if not queue_id:
        print(json.dumps({
            "status": "NO_POST",
            "reason": "NO_AI_APPROVED_SLOT_CANDIDATE",
            "account_id": args.account_id,
            "slot_id": args.slot_id,
        }, ensure_ascii=False))
        return 0

    activation = [
        sys.executable,
        "scripts/scheduled_publish_activation_gate.py",
        "--use-sheets",
    ]
    rc, _activation_payload = run_stage("runtime_activation_gate", activation, safe_env)
    if rc != 0:
        print(json.dumps({
            "status": "NO_POST",
            "reason": "RUNTIME_ACTIVATION_GATE_BLOCKED",
            "account_id": args.account_id,
            "slot_id": args.slot_id,
            "queue_id": queue_id,
        }, ensure_ascii=False))
        return 0

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
    print(json.dumps({
        "status": "PASS" if rc == 0 else "FAILED",
        "account_id": args.account_id,
        "slot_id": args.slot_id,
        "selected_queue_id": queue_id,
        "publish_status": publish_payload.get("status", ""),
    }, ensure_ascii=False, indent=2))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
