"""Verify and repair observation reservations; never publish or change a queue.

Only the existing metrics_collection_jobs sheet is written. A single bounded
RAW append is followed by an uncached read. No append retry is made, including
after transport errors. This is NOT a cross-process lock or Sheets CAS: callers
must serialize reservation writers and stop for reconciliation after uncertainty.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from metrics_collection_schedule import WINDOW_HOURS, _parse_time, build_metric_collection_jobs

VERIFIED_STATUSES = frozenset({"READ_AFTER_WRITE_PASS", "PASS", "VERIFIED"})
JOB_STATUSES = frozenset({"SCHEDULED", "DUE", "RETRY", "COMPLETE", "COMPLETE_PARTIAL", "FAILED"})
JOB_HEADERS = (
    "job_id", "result_id", "canary_id", "account_id", "platform", "post_url",
    "window_hours", "scheduled_for", "status", "attempt_count",
    "last_attempt_at", "last_error", "created_at", "updated_at",
)


class ReservationBlocked(RuntimeError):
    """Static, secret-free diagnostic; no provider exception text."""


def plan_reservations(
    posted: list[dict[str, Any]], existing: list[dict[str, Any]], *,
    account_id: str, result_id: str, now: datetime | None = None,
) -> dict[str, Any]:
    """Plan one verified result, rejecting collisions instead of overwriting rows."""
    if not account_id or not result_id:
        raise ReservationBlocked("reservation_identity_required")
    results = [r for r in posted if str(r.get("result_id", "")) == result_id]
    if len(results) != 1:
        raise ReservationBlocked("posted_result_missing_or_ambiguous")
    result = results[0]
    if (str(result.get("account_id", "")) != account_id
            or str(result.get("platform", "")).lower() != "threads"
            or str(result.get("status", "")).upper() != "POSTED"
            or str(result.get("verification_status", "")).upper() not in VERIFIED_STATUSES
            or not str(result.get("external_post_id", "")).strip()):
        raise ReservationBlocked("posted_result_not_verified_for_account")
    expected = build_metric_collection_jobs([result], [], now=now)
    if len(expected) != len(WINDOW_HOURS):
        raise ReservationBlocked("posted_result_schedule_fields_missing")
    missing = []
    confirmed = []
    for wanted in expected:
        # Look across ALL accounts. The legacy job ID is globally result-scoped;
        # filtering first would conceal a collision in another account.
        matches = [job for job in existing
                   if str(job.get("job_id", "")) == wanted["job_id"]
                   or (str(job.get("result_id", "")) == result_id
                       and str(job.get("window_hours", "")) == str(wanted["window_hours"]))]
        if not matches:
            missing.append(wanted)
            continue
        if len(matches) != 1:
            raise ReservationBlocked("metric_reservation_duplicate")
        job = matches[0]
        for field in ("job_id", "result_id", "account_id", "platform", "post_url", "window_hours"):
            if str(job.get(field, "")) != str(wanted[field]):
                raise ReservationBlocked("metric_reservation_identity_conflict")
        if (_parse_time(job.get("scheduled_for")) != _parse_time(wanted["scheduled_for"])
                or str(job.get("status", "")).upper() not in JOB_STATUSES):
            # CANCELLED is deliberate and cannot silently become a fresh job.
            raise ReservationBlocked("metric_reservation_state_conflict")
        confirmed.append(wanted["job_id"])
    return {"account_id": account_id, "result_id": result_id,
            "verified_count": len(confirmed), "verified_job_ids": confirmed,
            "missing_count": len(missing), "jobs": missing,
            "status": "VERIFIED" if not missing else "MISSING_RESERVATIONS"}


def read_table(client: Any, logical: str) -> tuple[list[str], list[dict[str, str]]]:
    """Bypass record caches and numeric coercion for large platform identifiers."""
    try:
        values = client._ws(logical).get_all_values()
    except Exception:
        raise ReservationBlocked("reservation_read_unavailable") from None
    if not values or not values[0] or len(values[0]) != len(set(values[0])):
        raise ReservationBlocked("reservation_schema_invalid")
    headers = values[0]
    return headers, [dict(zip(headers, row + [""] * (len(headers) - len(row))))
                     for row in values[1:] if any(row)]


def read_reservation_plan(client: Any, *, account_id: str, result_id: str) -> dict[str, Any]:
    _, posted = read_table(client, "posted_results")
    _, existing = read_table(client, "metrics_collection_jobs")
    return plan_reservations(posted, existing, account_id=account_id, result_id=result_id)


def reserve_metrics(client: Any, *, account_id: str, result_id: str, apply: bool = False) -> dict[str, Any]:
    """One fresh plan, at most one append, verified total rather than added count.

    An ambiguous append that is fully visible at readback is reconciled by
    reading only. Any other ambiguous outcome requires operator inspection;
    do not schedule this repair CLI as an automatic retry loop.
    """
    _, posted = read_table(client, "posted_results")
    headers, existing = read_table(client, "metrics_collection_jobs")
    plan = plan_reservations(posted, existing, account_id=account_id, result_id=result_id)
    if not apply or not plan["jobs"]:
        return {**plan, "append_attempted": False}
    if getattr(client, "dry_run", False):
        raise ReservationBlocked("reservation_dry_run_client")
    if not set(JOB_HEADERS).issubset(headers):
        raise ReservationBlocked("reservation_schema_incomplete")
    rows = [[str(job.get(header, "")) for header in headers] for job in plan["jobs"]]
    # No generic Sheets retry wrapper: an append may have succeeded even if
    # the response was lost. Readback is the ONLY recovery in this invocation.
    try:
        client._ws("metrics_collection_jobs").append_rows(rows, value_input_option="RAW")
    except Exception:
        pass
    try:
        verified = read_reservation_plan(client, account_id=account_id, result_id=result_id)
    except ReservationBlocked:
        raise ReservationBlocked("metric_reservation_outcome_unknown_manual_reconciliation") from None
    if verified["missing_count"]:
        raise ReservationBlocked("metric_reservation_outcome_unknown_manual_reconciliation")
    return {**verified, "append_attempted": True}
