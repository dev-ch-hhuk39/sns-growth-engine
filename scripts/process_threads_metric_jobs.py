#!/usr/bin/env python3
"""Consume due Threads metric jobs through the official Insights API."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT),
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

from collect_threads_metrics import (  # noqa: E402
    METRIC_KEYS,
    _append_row,
    _update_posted_result,
    build_snapshot,
    collect_api_threads_metrics,
)
from metrics_collection_schedule import (  # noqa: E402
    MAX_JOB_ATTEMPTS,
    due_jobs,
    next_job_status,
)
from publishers.threads_credentials import (  # noqa: E402
    resolve_credentials,
)

ALLOWED_ACCOUNTS = {
    "night_scout",
    "liver_manager",
}

VERIFIED_RESULT_STATUSES = {
    "READ_AFTER_WRITE_PASS",
    "PASS",
    "VERIFIED",
}


def now_iso() -> str:
    return datetime.now(
        timezone.utc
    ).isoformat()


def _integer(value: Any) -> int:
    try:
        return int(
            float(
                str(value or "0")
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0


FATAL_PREFLIGHT_ERRORS = {
    "posted_result_missing",
    "posted_result_platform_invalid",
    "posted_result_not_posted",
}

RETRYABLE_PREFLIGHT_ERRORS = {
    "external_post_id_missing",
    "read_after_write_not_verified",
}


def _posted_preflight_error(
    result: dict[str, Any] | None,
) -> str:
    if result is None:
        return "posted_result_missing"

    if str(
        result.get(
            "platform",
            "threads",
        )
    ).lower() != "threads":
        return (
            "posted_result_platform_invalid"
        )

    if str(
        result.get(
            "status",
            "",
        )
    ).upper() != "POSTED":
        return "posted_result_not_posted"

    if not str(
        result.get(
            "external_post_id",
            "",
        )
    ).strip():
        return "external_post_id_missing"

    if str(
        result.get(
            "verification_status",
            "",
        )
    ).upper() not in VERIFIED_RESULT_STATUSES:
        return (
            "read_after_write_not_verified"
        )

    return ""


def classify_due_work(
    posted_results: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    *,
    account_id: str = "all",
    result_id: str = "",
    max_jobs: int = 20,
    now: datetime | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Classify due jobs into collect, cancel, or deferred work."""

    posted_by_result = {
        str(
            row.get(
                "result_id",
                "",
            )
        ): dict(row)
        for row in posted_results
        if str(
            row.get(
                "result_id",
                "",
            )
        )
    }

    collect_targets: list[
        dict[str, Any]
    ] = []

    cancel_jobs: list[
        dict[str, Any]
    ] = []

    deferred_jobs: list[
        dict[str, Any]
    ] = []

    inspected = 0

    for job in due_jobs(
        jobs,
        now=now,
    ):
        job_account = str(
            job.get(
                "account_id",
                "",
            )
        )

        job_result_id = str(
            job.get(
                "result_id",
                "",
            )
        )

        if (
            account_id != "all"
            and job_account
            != account_id
        ):
            continue

        if (
            result_id
            and job_result_id
            != result_id
        ):
            continue

        if inspected >= max_jobs:
            break

        inspected += 1

        result = posted_by_result.get(
            job_result_id
        )

        preflight_error = (
            _posted_preflight_error(
                result
            )
        )

        lifecycle_row = {
            "job_id": str(
                job.get(
                    "job_id",
                    "",
                )
            ),
            "result_id": job_result_id,
            "account_id": (
                job_account
                or str(
                    (result or {}).get(
                        "account_id",
                        "",
                    )
                )
            ),
            "attempt_count": _integer(
                job.get(
                    "attempt_count",
                    0,
                )
            ),
            "error_reason": (
                preflight_error
            ),
            "window_hours": (
                job.get(
                    "window_hours",
                    "",
                )
            ),
            "scheduled_for": str(
                job.get(
                    "scheduled_for",
                    "",
                )
            ),
        }

        if preflight_error:
            if (
                preflight_error
                in FATAL_PREFLIGHT_ERRORS
            ):
                cancel_jobs.append(
                    lifecycle_row
                )
            else:
                deferred_jobs.append(
                    lifecycle_row
                )

            continue

        assert result is not None

        collect_targets.append(
            {
                **result,
                "result_id": job_result_id,
                "account_id": (
                    job_account
                    or result.get(
                        "account_id",
                        "",
                    )
                ),
                "platform": "threads",
                "post_url": (
                    result.get(
                        "post_url",
                        "",
                    )
                    or job.get(
                        "post_url",
                        "",
                    )
                ),
                "collection_job_id": (
                    job.get(
                        "job_id",
                        "",
                    )
                ),
                "collection_window_hours": (
                    job.get(
                        "window_hours",
                        "",
                    )
                ),
                "collection_scheduled_for": (
                    job.get(
                        "scheduled_for",
                        "",
                    )
                ),
                "collection_attempt_count": (
                    _integer(
                        job.get(
                            "attempt_count",
                            0,
                        )
                    )
                ),
                "collection_preflight_error": "",
            }
        )

    return {
        "collect": collect_targets,
        "cancel": cancel_jobs,
        "defer": deferred_jobs,
    }


def select_due_targets(
    posted_results: list[dict[str, Any]],
    jobs: list[dict[str, Any]],
    *,
    account_id: str = "all",
    result_id: str = "",
    max_jobs: int = 20,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Compatibility wrapper returning only API collection targets."""

    return classify_due_work(
        posted_results,
        jobs,
        account_id=account_id,
        result_id=result_id,
        max_jobs=max_jobs,
        now=now,
    )["collect"]


def _headers(ws) -> list[str]:
    return ws.row_values(1)


def update_collection_job(
    client,
    *,
    job_id: str,
    status: str,
    attempt_count: int,
    error_reason: str,
    attempted_at: str,
) -> None:
    ws = client._ws(
        "metrics_collection_jobs"
    )

    headers = _headers(ws)

    if "job_id" not in headers:
        raise KeyError(
            "metrics_collection_jobs."
            "job_id header missing"
        )

    cell = ws.find(
        job_id,
        in_column=(
            headers.index("job_id")
            + 1
        ),
    )

    if cell is None:
        raise KeyError(
            f"job_id={job_id!r} "
            "not found"
        )

    fields = {
        "status": status,
        "attempt_count": (
            attempt_count
        ),
        "last_attempt_at": (
            attempted_at
        ),
        "last_error": (
            error_reason
        ),
        "updated_at": (
            attempted_at
        ),
    }

    for field, value in fields.items():
        if field not in headers:
            continue

        ws.update_cell(
            cell.row,
            headers.index(field) + 1,
            str(value),
        )


def load_state(
    *,
    apply: bool,
) -> tuple[
    Any,
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    from config_loader import (
        get_config,
    )
    from sheets_client import (
        SheetsClient,
    )

    cfg = get_config()

    client = SheetsClient(
        cfg["sheet_id"],
        cfg["sa_dict"],
        dry_run=not apply,
    )

    posted = [
        dict(row)
        for row in client._ws(
            "posted_results"
        ).get_all_records()
    ]

    jobs = [
        dict(row)
        for row in client._ws(
            "metrics_collection_jobs"
        ).get_all_records()
    ]

    return client, posted, jobs


def collect_target(
    target: dict[str, Any],
) -> dict[str, Any]:
    account_id = str(
        target.get(
            "account_id",
            "",
        )
    )

    preflight_error = str(
        target.get(
            "collection_preflight_error",
            "",
        )
    )

    if preflight_error:
        metrics = {
            key: None
            for key in METRIC_KEYS
        }

        confidence = "none"
        error_reason = (
            preflight_error
        )
    else:
        credentials = (
            resolve_credentials(
                account_id
            )
        )

        (
            metrics,
            confidence,
            error_reason,
        ) = collect_api_threads_metrics(
            target,
            str(
                credentials.get(
                    "access_token",
                    "",
                )
            ),
        )

    snapshot = build_snapshot(
        row=target,
        source="api",
        confidence=confidence,
        metrics=metrics,
        memo=(
            "Official Threads post "
            "insights collection. "
            "Optional conversion metrics "
            "remain null unless separately "
            "measured."
        ),
        error_reason=error_reason,
    )

    attempt_count = (
        _integer(
            target.get(
                "collection_attempt_count",
                0,
            )
        )
        + 1
    )

    job_status = next_job_status(
        metrics_status=str(
            snapshot.get(
                "metrics_status",
                "",
            )
        ),
        collection_status=str(
            snapshot.get(
                "collection_status",
                "",
            )
        ),
        attempt_count=attempt_count,
    )

    return {
        "snapshot": snapshot,
        "attempt_count": (
            attempt_count
        ),
        "job_status": job_status,
        "error_reason": (
            error_reason
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Consume due Threads metric "
            "collection jobs safely"
        )
    )

    parser.add_argument(
        "--account-id",
        default="all",
        choices=[
            "all",
            "night_scout",
            "liver_manager",
        ],
    )

    parser.add_argument(
        "--result-id",
        default="",
    )

    parser.add_argument(
        "--max-jobs",
        type=int,
        default=20,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
    )

    parser.add_argument(
        "--confirm-metrics",
        action="store_true",
    )

    parser.add_argument(
        "--use-sheets",
        action="store_true",
    )

    args = parser.parse_args()

    if (
        args.max_jobs < 1
        or args.max_jobs > 50
    ):
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": (
                        "--max-jobs must "
                        "be 1..50"
                    ),
                }
            )
        )

        return 1

    if not args.use_sheets:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "reason": (
                        "--use-sheets is "
                        "required"
                    ),
                }
            )
        )

        return 1

    apply = bool(args.apply)

    client, posted, jobs = (
        load_state(
            apply=apply,
        )
    )

    work = classify_due_work(
        posted,
        jobs,
        account_id=args.account_id,
        result_id=args.result_id,
        max_jobs=args.max_jobs,
    )

    targets = work["collect"]
    cancel_jobs = work["cancel"]
    deferred_jobs = work["defer"]

    plan = {
        "status": (
            "WILL_APPLY"
            if apply
            else "PLAN_ONLY"
        ),
        "account_id": args.account_id,
        "due_job_count": (
            len(targets)
            + len(cancel_jobs)
            + len(deferred_jobs)
        ),
        "collection_job_count": (
            len(targets)
        ),
        "cancellation_job_count": (
            len(cancel_jobs)
        ),
        "deferred_job_count": (
            len(deferred_jobs)
        ),
        "job_ids": [
            str(
                row.get(
                    "collection_job_id",
                    "",
                )
            )
            for row in targets
        ],
        "cancellation_job_ids": [
            str(
                row.get(
                    "job_id",
                    "",
                )
            )
            for row in cancel_jobs
        ],
        "deferred_job_ids": [
            str(
                row.get(
                    "job_id",
                    "",
                )
            )
            for row in deferred_jobs
        ],
        "preflight_error_counts": dict(
            Counter(
                [
                    "NONE"
                    for _ in targets
                ]
                + [
                    str(
                        row.get(
                            "error_reason",
                            "",
                        )
                    )
                    for row in (
                        cancel_jobs
                        + deferred_jobs
                    )
                ]
            )
        ),
        "external_requests_planned": (
            sum(
                not bool(
                    row.get(
                        "collection_"
                        "preflight_error"
                    )
                )
                for row in targets
            )
            if apply
            else 0
        ),
        "snapshot_writes_planned": (
            len(targets)
            if apply
            else 0
        ),
        "job_state_writes_planned": (
            (
                len(targets)
                + len(cancel_jobs)
                + len(deferred_jobs)
            )
            if apply
            else 0
        ),
    }

    if not apply:
        print(
            json.dumps(
                plan,
                ensure_ascii=False,
                indent=2,
            )
        )

        return 0

    if not args.confirm_metrics:
        print(
            json.dumps(
                {
                    **plan,
                    "status": "BLOCKED",
                    "reason": (
                        "--apply requires "
                        "--confirm-metrics"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        return 1

    if not (
        targets
        or cancel_jobs
        or deferred_jobs
    ):
        print(
            json.dumps(
                {
                    **plan,
                    "status": (
                        "NO_DUE_JOBS"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        return 0

    status_counts: Counter[str] = (
        Counter()
    )

    snapshot_counts: Counter[str] = (
        Counter()
    )

    result_ids: list[str] = []

    for job in cancel_jobs:
        attempted_at = now_iso()

        attempt_count = (
            _integer(
                job.get(
                    "attempt_count",
                    0,
                )
            )
            + 1
        )

        update_collection_job(
            client,
            job_id=str(
                job.get(
                    "job_id",
                    "",
                )
            ),
            status="CANCELLED",
            attempt_count=attempt_count,
            error_reason=str(
                job.get(
                    "error_reason",
                    "",
                )
            ),
            attempted_at=attempted_at,
        )

        status_counts[
            "CANCELLED"
        ] += 1

    for job in deferred_jobs:
        attempted_at = now_iso()

        attempt_count = (
            _integer(
                job.get(
                    "attempt_count",
                    0,
                )
            )
            + 1
        )

        deferred_status = (
            "FAILED"
            if (
                attempt_count
                >= MAX_JOB_ATTEMPTS
            )
            else "RETRY"
        )

        update_collection_job(
            client,
            job_id=str(
                job.get(
                    "job_id",
                    "",
                )
            ),
            status=deferred_status,
            attempt_count=attempt_count,
            error_reason=str(
                job.get(
                    "error_reason",
                    "",
                )
            ),
            attempted_at=attempted_at,
        )

        status_counts[
            deferred_status
        ] += 1

    for target in targets:
        outcome = collect_target(
            target
        )

        snapshot = dict(
            outcome["snapshot"]
        )

        _append_row(
            client,
            "metric_snapshots",
            snapshot,
        )

        if str(
            snapshot.get(
                "metrics_status",
                "",
            )
        ).upper() in {
            "PARTIAL",
            "MEASURED",
        }:
            _update_posted_result(
                client,
                str(
                    snapshot.get(
                        "result_id",
                        "",
                    )
                ),
                snapshot,
            )

        attempted_at = now_iso()

        update_collection_job(
            client,
            job_id=str(
                target.get(
                    "collection_job_id",
                    "",
                )
            ),
            status=str(
                outcome["job_status"]
            ),
            attempt_count=int(
                outcome[
                    "attempt_count"
                ]
            ),
            error_reason=str(
                outcome[
                    "error_reason"
                ]
            ),
            attempted_at=attempted_at,
        )

        status_counts[
            str(
                outcome["job_status"]
            )
        ] += 1

        snapshot_counts[
            str(
                snapshot.get(
                    "metrics_status",
                    "",
                )
            )
        ] += 1

        result_ids.append(
            str(
                snapshot.get(
                    "result_id",
                    "",
                )
            )
        )

    print(
        json.dumps(
            {
                **plan,
                "status": "APPLIED",
                "processed_job_count": (
                    len(targets)
                    + len(cancel_jobs)
                    + len(deferred_jobs)
                ),
                "collection_job_count": (
                    len(targets)
                ),
                "cancelled_job_count": (
                    len(cancel_jobs)
                ),
                "deferred_job_count": (
                    len(deferred_jobs)
                ),
                "job_status_counts": (
                    dict(status_counts)
                ),
                "snapshot_status_counts": (
                    dict(
                        snapshot_counts
                    )
                ),
                "result_ids": result_ids,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
