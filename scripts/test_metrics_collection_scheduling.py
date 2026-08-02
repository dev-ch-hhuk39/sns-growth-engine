#!/usr/bin/env python3
from datetime import datetime, timezone

from metrics_collection_schedule import (
    build_metric_collection_jobs,
    due_jobs,
    next_job_status,
)

posted = [
    {
        "result_id": "r1",
        "account_id": "night_scout",
        "platform": "threads",
        "post_url": (
            "https://www.threads.com/"
            "@a/post/x"
        ),
        "posted_at": (
            "2026-07-20T00:00:00+00:00"
        ),
    }
]

now = datetime(
    2026,
    7,
    24,
    tzinfo=timezone.utc,
)

jobs = build_metric_collection_jobs(
    posted,
    [],
    now=now,
)

assert [
    job["window_hours"]
    for job in jobs
] == [24, 72, 168]

assert [
    job["status"]
    for job in jobs
] == [
    "DUE",
    "DUE",
    "SCHEDULED",
]

assert (
    build_metric_collection_jobs(
        posted,
        jobs,
        now=now,
    )
    == []
)

assert len(
    due_jobs(
        jobs,
        now=now,
    )
) == 2

retry = {
    **jobs[0],
    "status": "RETRY",
}

complete = {
    **jobs[1],
    "status": "COMPLETE",
}

assert len(
    due_jobs(
        [
            retry,
            complete,
        ],
        now=now,
    )
) == 1

assert next_job_status(
    metrics_status="MEASURED",
    collection_status="AVAILABLE",
    attempt_count=1,
) == "COMPLETE"

assert next_job_status(
    metrics_status="PARTIAL",
    collection_status="PARTIAL",
    attempt_count=1,
) == "RETRY"

assert next_job_status(
    metrics_status="PARTIAL",
    collection_status="PARTIAL",
    attempt_count=3,
) == "COMPLETE_PARTIAL"

assert next_job_status(
    metrics_status="UNAVAILABLE",
    collection_status="AUTH_ERROR",
    attempt_count=3,
) == "FAILED"

assert next_job_status(
    metrics_status="UNAVAILABLE",
    collection_status="POST_NOT_FOUND",
    attempt_count=1,
) == "FAILED"

print(
    "PASS "
    "test_metrics_collection_scheduling.py"
)
