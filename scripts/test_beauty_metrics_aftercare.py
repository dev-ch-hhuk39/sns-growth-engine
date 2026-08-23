#!/usr/bin/env python3
"""Beauty metrics and attribution stay account-scoped in production aftercare."""
from __future__ import annotations

from pathlib import Path

from process_threads_metric_jobs import ALLOWED_ACCOUNTS, classify_due_work

ROOT = Path(__file__).resolve().parents[1]


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"  PASS {message}")


posted = [
    {
        "result_id": "beauty-result",
        "account_id": "beauty_account",
        "platform": "threads",
        "status": "POSTED",
        "verification_status": "READ_AFTER_WRITE_PASS",
        "external_post_id": "beauty-post-id",
    },
    {
        "result_id": "night-result",
        "account_id": "night_scout",
        "platform": "threads",
        "status": "POSTED",
        "verification_status": "READ_AFTER_WRITE_PASS",
        "external_post_id": "night-post-id",
    },
]
jobs = [
    {
        "job_id": "beauty-job",
        "result_id": "beauty-result",
        "account_id": "beauty_account",
        "scheduled_for": "2026-08-22T00:00:00+00:00",
        "status": "SCHEDULED",
        "window_hours": 24,
    },
    {
        "job_id": "night-job",
        "result_id": "night-result",
        "account_id": "night_scout",
        "scheduled_for": "2026-08-22T00:00:00+00:00",
        "status": "SCHEDULED",
        "window_hours": 24,
    },
]

check("beauty_account" in ALLOWED_ACCOUNTS, "metric worker allows Beauty")
beauty_work = classify_due_work(posted, jobs, account_id="beauty_account")
check(
    [row["collection_job_id"] for row in beauty_work["collect"]] == ["beauty-job"],
    "Beauty metric selection excludes other accounts",
)

collector_source = (ROOT / "scripts/collect_threads_metrics.py").read_text(encoding="utf-8")
check(
    "beauty_account metrics collection is disabled" not in collector_source,
    "standalone collector does not block Beauty",
)

attribution_source = (ROOT / "scripts/run_growth_attribution_cycle.py").read_text(encoding="utf-8")
check(
    '"beauty_account"' in attribution_source,
    "attribution CLI accepts Beauty account scope",
)

workflow = (ROOT / ".github/workflows/production-autopilot-aftercare.yml").read_text(
    encoding="utf-8"
)
check(
    "secrets.THREADS_ACCESS_TOKEN_BEAUTY_ACCOUNT" in workflow,
    "scheduled aftercare receives Beauty metric credential",
)
check(
    '--account-id all' in workflow,
    "scheduled aftercare processes all accounts",
)

print("PASS test_beauty_metrics_aftercare.py")
