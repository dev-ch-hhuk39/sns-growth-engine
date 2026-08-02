"""Pure scheduling contract for post-publication Threads metrics collection."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

WINDOW_HOURS = (24, 72, 168)

TERMINAL_JOB_STATUSES = {
    "COMPLETE",
    "COMPLETE_PARTIAL",
    "FAILED",
    "CANCELLED",
}

MAX_JOB_ATTEMPTS = 3


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(
            str(value).replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def _window(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def build_metric_collection_jobs(
    posted_results: list[dict[str, Any]],
    existing_jobs: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Create missing 24h/72h/7d jobs without mutating inputs."""

    now = now or datetime.now(
        timezone.utc
    )

    existing_keys = {
        (
            str(job.get("result_id", "")),
            _window(
                job.get("window_hours")
            ),
        )
        for job in existing_jobs
        if str(
            job.get("status", "")
        ).upper()
        != "CANCELLED"
    }

    jobs: list[dict[str, Any]] = []

    for result in posted_results:
        if str(
            result.get(
                "platform",
                "threads",
            )
        ).lower() != "threads":
            continue

        result_id = str(
            result.get("result_id", "")
        )

        posted_at = _parse_time(
            result.get("posted_at")
        )

        if (
            not result_id
            or not posted_at
            or not str(
                result.get(
                    "post_url",
                    "",
                )
            ).strip()
        ):
            continue

        for window_hours in WINDOW_HOURS:
            key = (
                result_id,
                window_hours,
            )

            if key in existing_keys:
                continue

            due = posted_at + timedelta(
                hours=window_hours
            )

            jobs.append(
                {
                    "job_id": (
                        f"metrics_{result_id}_"
                        f"{window_hours}h"
                    ),
                    "result_id": result_id,
                    "canary_id": result.get(
                        "canary_id",
                        "",
                    ),
                    "account_id": result.get(
                        "account_id",
                        "",
                    ),
                    "platform": "threads",
                    "post_url": result.get(
                        "post_url",
                        "",
                    ),
                    "window_hours": (
                        window_hours
                    ),
                    "scheduled_for": (
                        due.isoformat()
                    ),
                    "status": (
                        "DUE"
                        if due <= now
                        else "SCHEDULED"
                    ),
                    "attempt_count": 0,
                    "last_attempt_at": "",
                    "last_error": "",
                    "created_at": (
                        now.isoformat()
                    ),
                    "updated_at": (
                        now.isoformat()
                    ),
                }
            )

    return jobs


def due_jobs(
    jobs: list[dict[str, Any]],
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    now = now or datetime.now(
        timezone.utc
    )

    selected: list[dict[str, Any]] = []

    for job in jobs:
        status = str(
            job.get("status", "")
        ).upper()

        if status in TERMINAL_JOB_STATUSES:
            continue

        scheduled_for = _parse_time(
            job.get("scheduled_for")
        )

        if (
            scheduled_for
            and scheduled_for <= now
        ):
            selected.append(
                dict(job)
            )

    selected.sort(
        key=lambda row: (
            str(
                row.get(
                    "scheduled_for",
                    "",
                )
            ),
            str(
                row.get(
                    "job_id",
                    "",
                )
            ),
        )
    )

    return selected


def next_job_status(
    *,
    metrics_status: str,
    collection_status: str,
    attempt_count: int,
) -> str:
    """Resolve the persisted state after one real collection attempt."""

    metrics = str(
        metrics_status or ""
    ).upper()

    collection = str(
        collection_status or ""
    ).upper()

    if metrics == "MEASURED":
        return "COMPLETE"

    if collection == "POST_NOT_FOUND":
        return "FAILED"

    if attempt_count >= MAX_JOB_ATTEMPTS:
        if metrics == "PARTIAL":
            return "COMPLETE_PARTIAL"

        return "FAILED"

    return "RETRY"
