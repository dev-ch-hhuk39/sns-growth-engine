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
    "beauty_account",
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


def _column_name(
    column: int,
) -> str:
    if column < 1:
        raise ValueError(
            "column must be >= 1"
        )

    letters: list[str] = []

    while column:
        column, remainder = divmod(
            column - 1,
            26,
        )

        letters.append(
            chr(
                ord("A")
                + remainder
            )
        )

    return "".join(
        reversed(letters)
    )


def _worksheet_table(
    ws,
) -> tuple[
    list[str],
    list[list[str]],
]:
    values = ws.get_all_values()

    if not values:
        return [], []

    headers = [
        str(value)
        for value in values[0]
    ]

    rows = []

    for values_row in values[1:]:
        padded = list(values_row) + [
            ""
        ] * max(
            0,
            len(headers)
            - len(values_row),
        )

        rows.append(
            padded[:len(headers)]
        )

    return headers, rows


def _indexed_rows(
    ws,
    key_header: str,
) -> tuple[
    list[str],
    dict[
        str,
        tuple[
            int,
            dict[str, str],
        ],
    ],
]:
    headers, rows = (
        _worksheet_table(ws)
    )

    if key_header not in headers:
        raise KeyError(
            f"{key_header} header missing"
        )

    indexed = {}

    for row_number, values in enumerate(
        rows,
        start=2,
    ):
        row = {
            header: values[index]
            for index, header
            in enumerate(headers)
        }

        key = str(
            row.get(
                key_header,
                "",
            )
        ).strip()

        if key:
            indexed[key] = (
                row_number,
                row,
            )

    return headers, indexed


def _batch_update_cells(
    ws,
    cells: dict[
        tuple[int, int],
        str,
    ],
) -> int:
    if not cells:
        return 0

    batch_update = getattr(
        ws,
        "batch_update",
        None,
    )

    if not callable(
        batch_update
    ):
        raise RuntimeError(
            "worksheet batch_update "
            "is required"
        )

    payload = [
        {
            "range": (
                f"{_column_name(column)}"
                f"{row_number}"
            ),
            "values": [
                [str(value)]
            ],
        }
        for (
            row_number,
            column,
        ), value in sorted(
            cells.items()
        )
    ]

    batch_update(
        payload,
        value_input_option=(
            "USER_ENTERED"
        ),
    )

    return len(payload)


def batch_update_collection_jobs(
    client,
    updates: list[dict[str, Any]],
) -> int:
    if not updates:
        return 0

    ws = client._ws(
        "metrics_collection_jobs"
    )

    headers, indexed = _indexed_rows(
        ws,
        "job_id",
    )

    cells: dict[
        tuple[int, int],
        str,
    ] = {}

    updated_job_ids = set()

    for update in updates:
        job_id = str(
            update.get(
                "job_id",
                "",
            )
        ).strip()

        if job_id not in indexed:
            raise KeyError(
                f"job_id={job_id!r} "
                "not found"
            )

        row_number, row = (
            indexed[job_id]
        )

        for field in (
            "status",
            "attempt_count",
            "last_attempt_at",
            "last_error",
            "updated_at",
        ):
            if field not in headers:
                continue

            value = str(
                update.get(
                    field,
                    "",
                )
            )

            row[field] = value

            cells[
                (
                    row_number,
                    headers.index(field)
                    + 1,
                )
            ] = value

        indexed[job_id] = (
            row_number,
            row,
        )

        updated_job_ids.add(
            job_id
        )

    _batch_update_cells(
        ws,
        cells,
    )

    return len(
        updated_job_ids
    )


def update_collection_job(
    client,
    *,
    job_id: str,
    status: str,
    attempt_count: int,
    error_reason: str,
    attempted_at: str,
) -> None:
    """Compatibility wrapper using one batch request."""

    batch_update_collection_jobs(
        client,
        [
            {
                "job_id": job_id,
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
        ],
    )


def batch_update_posted_results(
    client,
    updates: list[
        tuple[
            str,
            dict[str, Any],
        ]
    ],
) -> int:
    if not updates:
        return 0

    ws = client._ws(
        "posted_results"
    )

    headers, indexed = _indexed_rows(
        ws,
        "result_id",
    )

    cells: dict[
        tuple[int, int],
        str,
    ] = {}

    updated_result_ids = set()

    for result_id, snapshot in updates:
        result_id = str(
            result_id
        ).strip()

        if result_id not in indexed:
            raise KeyError(
                f"result_id={result_id!r} "
                "not found"
            )

        row_number, row = (
            indexed[result_id]
        )

        for key in METRIC_KEYS:
            if key not in headers:
                continue

            value = snapshot.get(key)

            if value is None:
                continue

            rendered = str(value)

            row[key] = rendered

            cells[
                (
                    row_number,
                    headers.index(key)
                    + 1,
                )
            ] = rendered

        incoming_status = str(
            snapshot.get(
                "metrics_status",
                "",
            )
        ).upper()

        existing_status = str(
            row.get(
                "metrics_status",
                "",
            )
        ).upper()

        should_write_status = (
            incoming_status
            == "MEASURED"
            or (
                incoming_status
                == "PARTIAL"
                and existing_status
                != "MEASURED"
            )
        )

        if (
            should_write_status
            and "metrics_status"
            in headers
        ):
            row["metrics_status"] = (
                incoming_status
            )

            cells[
                (
                    row_number,
                    headers.index(
                        "metrics_status"
                    )
                    + 1,
                )
            ] = incoming_status

        if "collected_at" in headers:
            collected_at = str(
                snapshot.get(
                    "collected_at",
                    "",
                )
            )

            row["collected_at"] = (
                collected_at
            )

            cells[
                (
                    row_number,
                    headers.index(
                        "collected_at"
                    )
                    + 1,
                )
            ] = collected_at

        if (
            "measurement_window"
            in headers
        ):
            window = snapshot.get(
                "collection_window_hours",
                "",
            )

            if window != "":
                rendered_window = (
                    f"{window}h"
                )

                row[
                    "measurement_window"
                ] = rendered_window

                cells[
                    (
                        row_number,
                        headers.index(
                            "measurement_window"
                        )
                        + 1,
                    )
                ] = rendered_window

        if "manual_memo" in headers:
            memo = str(
                snapshot.get(
                    "memo",
                    "",
                )
            )

            error_reason = str(
                snapshot.get(
                    "error_reason",
                    "",
                )
            )

            if error_reason:
                memo = (
                    f"{memo} "
                    f"error={error_reason}"
                ).strip()

            row["manual_memo"] = memo

            cells[
                (
                    row_number,
                    headers.index(
                        "manual_memo"
                    )
                    + 1,
                )
            ] = memo

        indexed[result_id] = (
            row_number,
            row,
        )

        updated_result_ids.add(
            result_id
        )

    _batch_update_cells(
        ws,
        cells,
    )

    return len(
        updated_result_ids
    )


def append_metric_snapshots(
    client,
    snapshots: list[
        dict[str, Any]
    ],
) -> dict[str, int]:
    if not snapshots:
        return {
            "added": 0,
            "skipped": 0,
        }

    from sheets_client import (
        TAB_DEFINITIONS,
    )

    client._ensure_tab(
        "metric_snapshots",
        TAB_DEFINITIONS[
            "metric_snapshots"
        ],
    )

    ws = client._ws(
        "metric_snapshots"
    )

    headers, rows = (
        _worksheet_table(ws)
    )

    if not headers:
        raise RuntimeError(
            "metric_snapshots "
            "headers missing"
        )

    if "snapshot_id" not in headers:
        raise KeyError(
            "metric_snapshots."
            "snapshot_id header missing"
        )

    snapshot_column = (
        headers.index(
            "snapshot_id"
        )
    )

    existing_ids = {
        str(
            row[snapshot_column]
        ).strip()
        for row in rows
        if snapshot_column
        < len(row)
        and str(
            row[snapshot_column]
        ).strip()
    }

    append_values = []

    seen = set(
        existing_ids
    )

    skipped = 0

    for snapshot in snapshots:
        snapshot_id = str(
            snapshot.get(
                "snapshot_id",
                "",
            )
        ).strip()

        if (
            not snapshot_id
            or snapshot_id in seen
        ):
            skipped += 1
            continue

        append_values.append(
            [
                ""
                if snapshot.get(
                    header
                ) is None
                else str(
                    snapshot.get(
                        header,
                        "",
                    )
                )
                for header in headers
            ]
        )

        seen.add(
            snapshot_id
        )

    if append_values:
        ws.append_rows(
            append_values,
            value_input_option=(
                "USER_ENTERED"
            ),
        )

    return {
        "added": len(
            append_values
        ),
        "skipped": skipped,
    }


def snapshots_by_job(
    snapshots: list[
        dict[str, Any]
    ],
) -> dict[
    str,
    list[dict[str, Any]],
]:
    grouped: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for snapshot in snapshots:
        job_id = str(
            snapshot.get(
                "collection_job_id",
                "",
            )
        ).strip()

        if not job_id:
            continue

        grouped.setdefault(
            job_id,
            [],
        ).append(
            dict(snapshot)
        )

    for rows in grouped.values():
        rows.sort(
            key=lambda row: (
                str(
                    row.get(
                        "collected_at",
                        "",
                    )
                ),
                str(
                    row.get(
                        "snapshot_id",
                        "",
                    )
                ),
            )
        )

    return grouped


def recoverable_snapshot_for_target(
    target: dict[str, Any],
    grouped_snapshots: dict[
        str,
        list[dict[str, Any]],
    ],
) -> dict[str, Any] | None:
    job_id = str(
        target.get(
            "collection_job_id",
            "",
        )
    ).strip()

    snapshots = grouped_snapshots.get(
        job_id,
        [],
    )

    committed_attempts = _integer(
        target.get(
            "collection_attempt_count",
            0,
        )
    )

    if (
        len(snapshots)
        > committed_attempts
    ):
        return dict(
            snapshots[-1]
        )

    return None


def load_state(
    *,
    apply: bool,
) -> tuple[
    Any,
    list[dict[str, Any]],
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

    try:
        snapshots = [
            dict(row)
            for row in client._ws(
                "metric_snapshots"
            ).get_all_records()
        ]
    except Exception:
        snapshots = []

    return (
        client,
        posted,
        jobs,
        snapshots,
    )


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
            "beauty_account",
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

    (
        client,
        posted,
        jobs,
        existing_snapshots,
    ) = load_state(
        apply=apply,
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

    grouped_snapshots = (
        snapshots_by_job(
            existing_snapshots
        )
    )

    recoverable_snapshots = {}

    for target in targets:
        snapshot = (
            recoverable_snapshot_for_target(
                target,
                grouped_snapshots,
            )
        )

        if snapshot is not None:
            recoverable_snapshots[
                str(
                    target.get(
                        "collection_job_id",
                        "",
                    )
                )
            ] = snapshot

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
        "recoverable_snapshot_count": (
            len(
                recoverable_snapshots
            )
        ),
        "external_requests_planned": (
            (
                len(targets)
                - len(
                    recoverable_snapshots
                )
            )
            if apply
            else 0
        ),
        "snapshot_writes_planned": (
            (
                len(targets)
                - len(
                    recoverable_snapshots
                )
            )
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

    new_snapshots: list[
        dict[str, Any]
    ] = []

    posted_result_updates: list[
        tuple[
            str,
            dict[str, Any],
        ]
    ] = []

    job_updates: list[
        dict[str, Any]
    ] = []

    reused_snapshot_count = 0
    external_request_count = 0

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

        job_updates.append(
            {
                "job_id": str(
                    job.get(
                        "job_id",
                        "",
                    )
                ),
                "status": "CANCELLED",
                "attempt_count": (
                    attempt_count
                ),
                "last_attempt_at": (
                    attempted_at
                ),
                "last_error": str(
                    job.get(
                        "error_reason",
                        "",
                    )
                ),
                "updated_at": (
                    attempted_at
                ),
            }
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

        job_updates.append(
            {
                "job_id": str(
                    job.get(
                        "job_id",
                        "",
                    )
                ),
                "status": (
                    deferred_status
                ),
                "attempt_count": (
                    attempt_count
                ),
                "last_attempt_at": (
                    attempted_at
                ),
                "last_error": str(
                    job.get(
                        "error_reason",
                        "",
                    )
                ),
                "updated_at": (
                    attempted_at
                ),
            }
        )

        status_counts[
            deferred_status
        ] += 1

    for target in targets:
        job_id = str(
            target.get(
                "collection_job_id",
                "",
            )
        )

        recovered_snapshot = (
            recoverable_snapshots.get(
                job_id
            )
        )

        if recovered_snapshot is not None:
            snapshot = dict(
                recovered_snapshot
            )

            attempt_count = (
                _integer(
                    target.get(
                        "collection_"
                        "attempt_count",
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
                attempt_count=(
                    attempt_count
                ),
            )

            outcome = {
                "snapshot": snapshot,
                "attempt_count": (
                    attempt_count
                ),
                "job_status": job_status,
                "error_reason": str(
                    snapshot.get(
                        "error_reason",
                        "",
                    )
                ),
            }

            reused_snapshot_count += 1
        else:
            outcome = collect_target(
                target
            )

            snapshot = dict(
                outcome["snapshot"]
            )

            new_snapshots.append(
                snapshot
            )

            external_request_count += 1

        if str(
            snapshot.get(
                "metrics_status",
                "",
            )
        ).upper() in {
            "PARTIAL",
            "MEASURED",
        }:
            posted_result_updates.append(
                (
                    str(
                        snapshot.get(
                            "result_id",
                            "",
                        )
                    ),
                    snapshot,
                )
            )

        attempted_at = now_iso()

        job_updates.append(
            {
                "job_id": job_id,
                "status": str(
                    outcome[
                        "job_status"
                    ]
                ),
                "attempt_count": int(
                    outcome[
                        "attempt_count"
                    ]
                ),
                "last_attempt_at": (
                    attempted_at
                ),
                "last_error": str(
                    outcome[
                        "error_reason"
                    ]
                ),
                "updated_at": (
                    attempted_at
                ),
            }
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

    # Recovery-safe order:
    # 1. append immutable snapshots
    # 2. merge posted-result metrics
    # 3. commit job lifecycle state last
    #
    # If any phase fails, the next run can detect
    # an uncommitted snapshot and resume without
    # issuing the same Threads API request again.
    snapshot_append_result = (
        append_metric_snapshots(
            client,
            new_snapshots,
        )
    )

    posted_result_rows_updated = (
        batch_update_posted_results(
            client,
            posted_result_updates,
        )
    )

    job_rows_updated = (
        batch_update_collection_jobs(
            client,
            job_updates,
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
                "external_request_count": (
                    external_request_count
                ),
                "reused_snapshot_count": (
                    reused_snapshot_count
                ),
                "new_snapshot_count": len(
                    new_snapshots
                ),
                "snapshot_append_result": (
                    snapshot_append_result
                ),
                "posted_result_rows_updated": (
                    posted_result_rows_updated
                ),
                "job_rows_updated": (
                    job_rows_updated
                ),
                "bounded_sheet_write_requests": (
                    int(
                        bool(
                            new_snapshots
                        )
                    )
                    + int(
                        bool(
                            posted_result_updates
                        )
                    )
                    + int(
                        bool(
                            job_updates
                        )
                    )
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
