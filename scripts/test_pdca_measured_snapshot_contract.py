#!/usr/bin/env python3
from generate_threads_ideas_from_references import (
    measured_pdca_snapshots,
)

posted = [
    {
        "result_id": "valid-result",
        "account_id": "night_scout",
        "platform": "threads",
        "status": "POSTED",
    },
    {
        "result_id": "pending-result",
        "account_id": "night_scout",
        "platform": "threads",
        "status": "PENDING",
    },
]

snapshots = [
    {
        "snapshot_id": "valid-zero-values",
        "result_id": "valid-result",
        "account_id": "night_scout",
        "platform": "threads",
        "metrics_status": "MEASURED",
        "views": 0,
        "likes": 0,
        "comments": 0,
        "collected_at": "2026-08-03T00:00:00+00:00",
    },
    {
        "snapshot_id": "missing-comments",
        "result_id": "valid-result",
        "account_id": "night_scout",
        "platform": "threads",
        "metrics_status": "MEASURED",
        "views": 100,
        "likes": 10,
        "comments": "",
        "collected_at": "2026-08-03T01:00:00+00:00",
    },
    {
        "snapshot_id": "wrong-platform",
        "result_id": "valid-result",
        "account_id": "night_scout",
        "platform": "x",
        "metrics_status": "MEASURED",
        "views": 100,
        "likes": 10,
        "comments": 2,
        "collected_at": "2026-08-03T02:00:00+00:00",
    },
    {
        "snapshot_id": "invalid-post-state",
        "result_id": "pending-result",
        "account_id": "night_scout",
        "platform": "threads",
        "metrics_status": "MEASURED",
        "views": 100,
        "likes": 10,
        "comments": 2,
        "collected_at": "2026-08-03T03:00:00+00:00",
    },
    {
        "snapshot_id": "other-account",
        "result_id": "valid-result",
        "account_id": "liver_manager",
        "platform": "threads",
        "metrics_status": "MEASURED",
        "views": 100,
        "likes": 10,
        "comments": 2,
        "collected_at": "2026-08-03T04:00:00+00:00",
    },
]

selected = measured_pdca_snapshots(
    snapshots,
    posted,
    account_id="night_scout",
)

assert [
    row["snapshot_id"]
    for row in selected
] == ["valid-zero-values"]

media_metrics = [
    {
        "snapshot_id": "media-only",
        "result_id": "valid-result",
        "account_id": "night_scout",
        "platform": "threads",
        "metrics_status": "MEASURED",
        "views": 500,
        "likes": 50,
        "comments": 5,
    }
]

assert measured_pdca_snapshots(
    [],
    posted,
    account_id="night_scout",
) == []

assert media_metrics[0]["snapshot_id"] == "media-only"

print(
    "PASS "
    "test_pdca_measured_snapshot_contract.py"
)
