#!/usr/bin/env python3
"""Soft Hybrid results reach promotion; only a hard promotion reject advances."""
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
    {"status": "APPLIED", "updated_queue_ids": []},
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
assert result["attempts"][0]["promotion_status"] == "APPLIED"
assert result["attempts"][1]["hybrid_status"] == "PASS"
print("PASS test_direct_media_preparation_loop_failover.py")


quota_calls = []

def quota_runner(command: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
    quota_calls.append(command)
    if any("ingest_direct_reference_media_reliable.py" in item for item in command):
        return subprocess.CompletedProcess(
            command, 1, "", "[SHEETS_RETRY] open_by_key failed with rate_limit; response body suppressed",
        )
    raise AssertionError("preparation must stop immediately after Sheets quota exhaustion")


quota_result = loop.execute(
    "night_scout", "ns_1800_direct_media", 5, runner=quota_runner,
)
assert quota_result["status"] == "SHEETS_QUOTA_DEFERRED"
assert quota_result["blocked_reasons"] == ["sheets_rate_limit_exhausted"]
assert len(quota_calls) == 1

provider_429 = subprocess.CompletedProcess(
    ["provider"], 1, "", "HTTP 429 from external media provider",
)
assert not loop._sheets_quota_exhausted(provider_429)

transient_sheet_retry = subprocess.CompletedProcess(
    ["sheets"], 0, "", "[SHEETS_RETRY] get_all_records:queue failed with rate_limit; retrying",
)
assert not loop._sheets_quota_exhausted(transient_sheet_retry)
print("PASS terminal Sheets quota stops candidate retry without classifying provider 429")
