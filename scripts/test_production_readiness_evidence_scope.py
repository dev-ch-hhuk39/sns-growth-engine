#!/usr/bin/env python3
"""Buffered acceptance excludes legacy gaps and accepts either real scheduler."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

from run_production_readiness_acceptance import buffered_run_verified, post_evidence_counts  # noqa: E402

post = {
    "account_id": "night_scout",
    "result_id": "result-buffered",
    "external_post_id": "123456789",
    "post_url": "https://www.threads.com/@night/post/example",
    "verification_status": "READ_AFTER_WRITE_PASS",
}
jobs = [
    {"account_id": "night_scout", "result_id": "result-buffered", "window_hours": str(hours)}
    for hours in (24, 72, 168)
]
assert post_evidence_counts([post], jobs) == {
    "duplicate_posts": 0,
    "unverified_posts": 0,
    "metrics_missing": 0,
}
legacy = {**post, "result_id": "legacy", "external_post_id": ""}
assert post_evidence_counts([legacy], []) == {
    "duplicate_posts": 0,
    "unverified_posts": 1,
    "metrics_missing": 1,
}

base = {
    "delivery_engine": "buffered_v1",
    "code_revision": "a" * 40,
    "status": "POSTED_PRIMARY",
    "result_id": "result-buffered",
}
assert buffered_run_verified({**base, "execution_trigger": "xserver_cron", "host_execution_id": "host-1"}, [post])
assert buffered_run_verified({**base, "execution_trigger": "github_schedule_recovery", "workflow_run_id": "run-1"}, [post])
assert not buffered_run_verified({**base, "execution_trigger": "xserver_cron", "host_execution_id": ""}, [post])
print("production readiness evidence scope: PASS")
