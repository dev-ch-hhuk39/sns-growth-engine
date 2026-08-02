#!/usr/bin/env python3
from datetime import datetime, timezone

from process_threads_metric_jobs import (
    classify_due_work,
    select_due_targets,
)

now = datetime(
    2026,
    8,
    3,
    tzinfo=timezone.utc,
)

posted = [
    {
        "result_id": "r1",
        "account_id": "night_scout",
        "platform": "threads",
        "status": "POSTED",
        "verification_status": (
            "READ_AFTER_WRITE_PASS"
        ),
        "external_post_id": "post-1",
        "post_url": (
            "https://www.threads.com/"
            "@a/post/one"
        ),
    },
    {
        "result_id": "r2",
        "account_id": "liver_manager",
        "platform": "threads",
        "status": "POSTED",
        "verification_status": (
            "PENDING"
        ),
        "external_post_id": "post-2",
        "post_url": (
            "https://www.threads.com/"
            "@b/post/two"
        ),
    },
    {
        "result_id": "r3",
        "account_id": "night_scout",
        "platform": "threads",
        "status": (
            "INVALID_CONTENT_CANARY"
        ),
        "verification_status": (
            "READ_AFTER_WRITE_PASS"
        ),
        "external_post_id": "post-3",
        "post_url": (
            "https://www.threads.com/"
            "@a/post/three"
        ),
    },
    {
        "result_id": "r4",
        "account_id": "night_scout",
        "platform": "threads",
        "status": "POSTED",
        "verification_status": (
            "READ_AFTER_WRITE_PASS"
        ),
        "external_post_id": "",
        "post_url": (
            "https://www.threads.com/"
            "@a/post/four"
        ),
    },
]

jobs = [
    {
        "job_id": "j1",
        "result_id": "r1",
        "account_id": "night_scout",
        "scheduled_for": (
            "2026-08-02T00:00:00+00:00"
        ),
        "status": "SCHEDULED",
        "attempt_count": 0,
        "window_hours": 24,
    },
    {
        "job_id": "j2",
        "result_id": "r2",
        "account_id": "liver_manager",
        "scheduled_for": (
            "2026-08-02T00:00:00+00:00"
        ),
        "status": "SCHEDULED",
        "attempt_count": 0,
        "window_hours": 24,
    },
    {
        "job_id": "j3",
        "result_id": "r1",
        "account_id": "night_scout",
        "scheduled_for": (
            "2026-08-05T00:00:00+00:00"
        ),
        "status": "SCHEDULED",
        "attempt_count": 0,
        "window_hours": 72,
    },
    {
        "job_id": "j4",
        "result_id": "r1",
        "account_id": "night_scout",
        "scheduled_for": (
            "2026-08-02T00:00:00+00:00"
        ),
        "status": "COMPLETE",
        "attempt_count": 1,
        "window_hours": 168,
    },
    {
        "job_id": "j5",
        "result_id": "r3",
        "account_id": "night_scout",
        "scheduled_for": (
            "2026-08-02T00:00:00+00:00"
        ),
        "status": "SCHEDULED",
        "attempt_count": 0,
        "window_hours": 24,
    },
    {
        "job_id": "j6",
        "result_id": "r4",
        "account_id": "night_scout",
        "scheduled_for": (
            "2026-08-02T00:00:00+00:00"
        ),
        "status": "SCHEDULED",
        "attempt_count": 1,
        "window_hours": 24,
    },
    {
        "job_id": "j7",
        "result_id": "missing",
        "account_id": "night_scout",
        "scheduled_for": (
            "2026-08-02T00:00:00+00:00"
        ),
        "status": "SCHEDULED",
        "attempt_count": 0,
        "window_hours": 24,
    },
]

work = classify_due_work(
    posted,
    jobs,
    now=now,
)

assert [
    row["collection_job_id"]
    for row in work["collect"]
] == ["j1"]

assert [
    row["job_id"]
    for row in work["cancel"]
] == [
    "j5",
    "j7",
]

assert [
    row["error_reason"]
    for row in work["cancel"]
] == [
    "posted_result_not_posted",
    "posted_result_missing",
]

assert [
    row["job_id"]
    for row in work["defer"]
] == [
    "j2",
    "j6",
]

assert [
    row["error_reason"]
    for row in work["defer"]
] == [
    "read_after_write_not_verified",
    "external_post_id_missing",
]

targets = select_due_targets(
    posted,
    jobs,
    now=now,
)

assert [
    row["collection_job_id"]
    for row in targets
] == ["j1"]

night_only = classify_due_work(
    posted,
    jobs,
    account_id="night_scout",
    now=now,
)

assert [
    row["collection_job_id"]
    for row in night_only["collect"]
] == ["j1"]

assert [
    row["job_id"]
    for row in night_only["cancel"]
] == [
    "j5",
    "j7",
]

assert [
    row["job_id"]
    for row in night_only["defer"]
] == ["j6"]

print(
    "PASS "
    "test_process_threads_metric_jobs.py"
)
