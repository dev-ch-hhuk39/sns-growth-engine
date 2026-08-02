#!/usr/bin/env python3

from pathlib import Path

from activation_route_contract import (
    ACCOUNTS,
    ACTIVATION_CANARY_TYPES,
)
from reconcile_canary_read_after_write import (
    build_plan,
)


FIRST_BATCH = (
    "fresh_first_wave_20260730021819"
)
REMAINING_BATCH = (
    "fresh_remaining_routes_20260730225046"
)

FIRST_WAVE_TYPES = {
    "original_text",
    "direct_reference_media",
}

posted = []
jobs = []

for account_id in ACCOUNTS:
    for content_route in (
        ACTIVATION_CANARY_TYPES
    ):
        batch_id = (
            FIRST_BATCH
            if content_route
            in FIRST_WAVE_TYPES
            else REMAINING_BATCH
        )

        canary_id = (
            f"canary_{batch_id}_"
            f"{account_id}_{content_route}"
        )

        result_id = (
            f"result_{account_id}_"
            f"{content_route}"
        )

        posted.append(
            {
                "result_id": result_id,
                "queue_id": (
                    f"queue_{account_id}_"
                    f"{content_route}"
                ),
                "account_id": account_id,
                "content_route": content_route,
                "content_type": content_route,
                "canary_id": canary_id,
                "batch_id": batch_id,
                "status": "POSTED",
                "post_url": (
                    "https://www.threads.com/"
                    "@example/post/test"
                ),
                "external_post_id": result_id,
                "verification_status": (
                    "PENDING"
                ),
            }
        )

        for window_hours in (
            24,
            72,
            168,
        ):
            jobs.append(
                {
                    "result_id": result_id,
                    "canary_id": canary_id,
                    "window_hours": (
                        window_hours
                    ),
                    "status": "SCHEDULED",
                }
            )


plan = build_plan(
    posted,
    jobs,
    first_wave_batch_id=FIRST_BATCH,
    remaining_batch_id=REMAINING_BATCH,
)

assert plan["status"] == "PASS", plan
assert plan["expected_count"] == 10
assert plan["row_count"] == 10

assert all(
    row["action"]
    == "UPDATE_VERIFICATION"
    for row in plan["rows"]
)


already_verified = [
    {
        **row,
        "verification_status": (
            "READ_AFTER_WRITE_PASS"
        ),
    }
    for row in posted
]

verified_plan = build_plan(
    already_verified,
    jobs,
    first_wave_batch_id=FIRST_BATCH,
    remaining_batch_id=REMAINING_BATCH,
)

assert verified_plan["status"] == "PASS"

assert all(
    row["action"]
    == "SKIP_ALREADY_VERIFIED"
    for row in verified_plan["rows"]
)


missing_metric_plan = build_plan(
    posted,
    jobs[:-1],
    first_wave_batch_id=FIRST_BATCH,
    remaining_batch_id=REMAINING_BATCH,
)

assert (
    missing_metric_plan["status"]
    == "BLOCKED"
)

assert any(
    "METRIC_WINDOWS_INCOMPLETE"
    in row["reasons"]
    for row in missing_metric_plan["rows"]
)


wrong_batch_plan = build_plan(
    posted,
    jobs,
    first_wave_batch_id=(
        "wrong_first_batch"
    ),
    remaining_batch_id=REMAINING_BATCH,
)

assert wrong_batch_plan["status"] == "BLOCKED"


processor = Path(
    "scripts/process_threads_queue.py"
).read_text(encoding="utf-8")

assert (
    '"verification_status": '
    '"READ_AFTER_WRITE_PASS"'
) in processor

assert (
    "READ_AFTER_WRITE_STATUS_NOT_PERSISTED"
    in processor
)

print(
    "PASS "
    "test_reconcile_canary_read_after_write.py"
)
