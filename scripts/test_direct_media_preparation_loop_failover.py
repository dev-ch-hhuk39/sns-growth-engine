#!/usr/bin/env python3
"""Hybrid candidate rejection advances to the next Direct media candidate."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import run_direct_media_preparation_loop as loop  # noqa: E402


responses = iter([
    {"status": "INGESTED_BUNDLE"},
    {"status": "PREPARED", "queue_id": "q_bad"},
    {"status": "PASS", "results": [{"queue_id": "q_bad", "status": "BLOCKED", "blocked_reasons": ["account_fit"]}]},
    {"status": "INGESTED_BUNDLE"},
    {"status": "PREPARED", "queue_id": "q_good"},
    {"status": "PASS", "results": [{"queue_id": "q_good", "status": "PASS", "blocked_reasons": []}]},
    {"status": "APPLIED", "updated_queue_ids": ["q_good"]},
])


def runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
    payload = next(responses)
    return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")


result = loop.execute(
    "night_scout",
    "ns_1800_direct_media",
    5,
    runner=runner,
)
assert result["status"] == "READY"
assert result["selected_queue_id"] == "q_good"
assert len(result["attempts"]) == 2
assert result["attempts"][0]["hybrid_status"] == "BLOCKED"
assert result["attempts"][1]["hybrid_status"] == "PASS"
print("PASS test_direct_media_preparation_loop_failover.py")
