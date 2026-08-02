#!/usr/bin/env python3
from __future__ import annotations

from collect_threads_metrics import (
    build_snapshot,
)
from process_threads_metric_jobs import (
    append_metric_snapshots,
    batch_update_collection_jobs,
    batch_update_posted_results,
    recoverable_snapshot_for_target,
    snapshots_by_job,
)


class FakeWorksheet:
    def __init__(
        self,
        headers,
        rows,
    ):
        self.values = [
            list(headers),
            *[
                list(row)
                for row in rows
            ],
        ]

        self.batch_calls = []
        self.append_calls = []

    def get_all_values(self):
        return [
            list(row)
            for row in self.values
        ]

    def batch_update(
        self,
        payload,
        value_input_option=None,
    ):
        self.batch_calls.append(
            {
                "payload": payload,
                "value_input_option": (
                    value_input_option
                ),
            }
        )

    def append_rows(
        self,
        rows,
        value_input_option=None,
    ):
        self.append_calls.append(
            {
                "rows": [
                    list(row)
                    for row in rows
                ],
                "value_input_option": (
                    value_input_option
                ),
            }
        )


class FakeClient:
    def __init__(self, worksheets):
        self.worksheets = worksheets
        self.ensure_calls = []

    def _ws(self, logical):
        return self.worksheets[logical]

    def _ensure_tab(
        self,
        logical,
        definition,
    ):
        self.ensure_calls.append(
            logical
        )


jobs_headers = [
    "job_id",
    "status",
    "attempt_count",
    "last_attempt_at",
    "last_error",
    "updated_at",
]

jobs_ws = FakeWorksheet(
    jobs_headers,
    [
        [
            "j1",
            "SCHEDULED",
            "0",
            "",
            "",
            "",
        ],
        [
            "j2",
            "SCHEDULED",
            "0",
            "",
            "",
            "",
        ],
    ],
)

posted_headers = [
    "result_id",
    "views",
    "likes",
    "comments",
    "metrics_status",
    "collected_at",
    "measurement_window",
    "manual_memo",
]

posted_ws = FakeWorksheet(
    posted_headers,
    [
        [
            "r1",
            "",
            "",
            "",
            "PENDING",
            "",
            "",
            "",
        ]
    ],
)

snapshot_headers = [
    "snapshot_id",
    "result_id",
    "account_id",
    "platform",
    "collection_job_id",
    "collection_window_hours",
    "metrics_status",
    "collection_status",
    "collected_at",
    "views",
    "likes",
    "comments",
]

snapshot_ws = FakeWorksheet(
    snapshot_headers,
    [
        [
            "existing-snapshot",
            "r1",
            "night_scout",
            "threads",
            "j1",
            "24",
            "MEASURED",
            "AVAILABLE",
            "2026-08-03T00:00:00+00:00",
            "10",
            "1",
            "0",
        ]
    ],
)

client = FakeClient(
    {
        "metrics_collection_jobs": (
            jobs_ws
        ),
        "posted_results": posted_ws,
        "metric_snapshots": (
            snapshot_ws
        ),
    }
)

updated_jobs = batch_update_collection_jobs(
    client,
    [
        {
            "job_id": "j1",
            "status": "COMPLETE",
            "attempt_count": 1,
            "last_attempt_at": "now",
            "last_error": "",
            "updated_at": "now",
        },
        {
            "job_id": "j2",
            "status": "CANCELLED",
            "attempt_count": 1,
            "last_attempt_at": "now",
            "last_error": (
                "posted_result_not_posted"
            ),
            "updated_at": "now",
        },
    ],
)

assert updated_jobs == 2
assert len(jobs_ws.batch_calls) == 1
assert len(
    jobs_ws.batch_calls[0]["payload"]
) == 10

snapshot_24 = {
    "result_id": "r1",
    "views": 10,
    "likes": 1,
    "comments": 0,
    "metrics_status": "MEASURED",
    "collected_at": (
        "2026-08-03T00:00:00+00:00"
    ),
    "collection_window_hours": 24,
    "memo": "24h",
    "error_reason": "",
}

snapshot_72 = {
    "result_id": "r1",
    "views": 20,
    "likes": 2,
    "comments": 1,
    "metrics_status": "MEASURED",
    "collected_at": (
        "2026-08-05T00:00:00+00:00"
    ),
    "collection_window_hours": 72,
    "memo": "72h",
    "error_reason": "",
}

updated_results = (
    batch_update_posted_results(
        client,
        [
            ("r1", snapshot_24),
            ("r1", snapshot_72),
        ],
    )
)

assert updated_results == 1
assert len(
    posted_ws.batch_calls
) == 1

payload = {
    item["range"]: item[
        "values"
    ][0][0]
    for item in posted_ws
    .batch_calls[0]["payload"]
}

assert payload["B2"] == "20"
assert payload["C2"] == "2"
assert payload["D2"] == "1"
assert payload["E2"] == "MEASURED"
assert payload["G2"] == "72h"
assert payload["H2"] == "72h"

append_result = append_metric_snapshots(
    client,
    [
        {
            "snapshot_id": (
                "existing-snapshot"
            ),
        },
        {
            "snapshot_id": (
                "new-snapshot"
            ),
            "result_id": "r2",
            "account_id": (
                "liver_manager"
            ),
            "platform": "threads",
            "collection_job_id": "j2",
            "collection_window_hours": 24,
            "metrics_status": "PARTIAL",
            "collection_status": "PARTIAL",
            "collected_at": (
                "2026-08-03T01:00:00+00:00"
            ),
            "views": 5,
            "likes": 1,
            "comments": "",
        },
        {
            "snapshot_id": (
                "new-snapshot"
            ),
        },
    ],
)

assert append_result == {
    "added": 1,
    "skipped": 2,
}

assert len(
    snapshot_ws.append_calls
) == 1

assert len(
    snapshot_ws
    .append_calls[0]["rows"]
) == 1

grouped = snapshots_by_job(
    [
        {
            "snapshot_id": "s1",
            "collection_job_id": "j1",
            "collected_at": "2026-08-03",
        }
    ]
)

recoverable = (
    recoverable_snapshot_for_target(
        {
            "collection_job_id": "j1",
            "collection_attempt_count": 0,
        },
        grouped,
    )
)

assert recoverable is not None
assert recoverable["snapshot_id"] == "s1"

already_committed = (
    recoverable_snapshot_for_target(
        {
            "collection_job_id": "j1",
            "collection_attempt_count": 1,
        },
        grouped,
    )
)

assert already_committed is None

first = build_snapshot(
    row={
        "result_id": "same-result",
        "account_id": "night_scout",
        "platform": "threads",
        "collection_job_id": "job-24h",
        "collection_window_hours": 24,
    },
    source="api",
    confidence="high",
    metrics={
        "views": 10,
        "likes": 1,
        "comments": 0,
        "reposts": 0,
        "quotes": 0,
        "profile_clicks": None,
        "follows": None,
        "line_adds": None,
    },
    memo="test",
)

second = build_snapshot(
    row={
        "result_id": "same-result",
        "account_id": "night_scout",
        "platform": "threads",
        "collection_job_id": "job-72h",
        "collection_window_hours": 72,
    },
    source="api",
    confidence="high",
    metrics={
        "views": 20,
        "likes": 2,
        "comments": 1,
        "reposts": 0,
        "quotes": 0,
        "profile_clicks": None,
        "follows": None,
        "line_adds": None,
    },
    memo="test",
)

assert (
    first["snapshot_id"]
    != second["snapshot_id"]
)

assert "job_24h" in first["snapshot_id"]
assert "job_72h" in second["snapshot_id"]

print(
    "PASS "
    "test_metric_job_batch_writes_and_resume.py"
)
