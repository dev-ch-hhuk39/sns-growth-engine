#!/usr/bin/env python3
"""Idempotent Sheets persistence for scheduled content slots."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from content_schedule import slot_by_id

JST = timezone(timedelta(hours=9))


def now_jst() -> datetime:
    return datetime.now(JST)


def slot_run_id(account_id: str, slot_id: str, at: datetime | None = None) -> str:
    date = (at or now_jst()).astimezone(JST).strftime("%Y%m%d")
    return f"slot_{date}_{account_id}_{slot_id}"


def build_slot_run(
    account_id: str,
    slot_id: str,
    *,
    status: str = "RUNNING",
    actual_post_type: str = "",
    fallback_level: int = 0,
    no_post_reason: str = "",
    now: datetime | None = None,
    **fields: Any,
) -> dict[str, Any]:
    local = (now or now_jst()).astimezone(JST)
    slot = slot_by_id(account_id, slot_id)
    if not slot:
        raise ValueError(f"unknown content slot: {account_id}/{slot_id}")
    target_date = local.date()
    target_hour, target_minute = map(int, str(slot["target_jst"]).split(":"))
    if target_hour >= 24:
        target_hour -= 24
        # The scheduled 25:00 worker starts at 00:45 on the actual calendar
        # day. Only a daytime/manual invocation refers to the following day.
        if local.hour >= 12:
            target_date += timedelta(days=1)
    target = datetime(target_date.year, target_date.month, target_date.day, target_hour, target_minute, tzinfo=JST)
    created = local.isoformat()
    row = {
        "slot_run_id": slot_run_id(account_id, slot_id, local),
        "schedule_date_jst": local.strftime("%Y-%m-%d"),
        "account_id": account_id,
        "slot_id": slot_id,
        "scheduled_target_at": target.isoformat(),
        "allowed_window_start": (target - timedelta(minutes=15)).isoformat(),
        "allowed_window_end": (target + timedelta(minutes=15)).isoformat(),
        "actual_started_at": created,
        "actual_posted_at": "",
        "expected_post_type": slot["post_type"],
        "actual_post_type": actual_post_type,
        "fallback_level": str(fallback_level),
        "status": status,
        "queue_id": "",
        "result_id": "",
        "post_url": "",
        "media_asset_id": "",
        "source_post_id": "",
        "source_video_id": "",
        "no_post_reason": no_post_reason,
        "last_error_redacted": "",
        "created_at": created,
        "updated_at": created,
    }
    row.update({key: "" if value is None else str(value) for key, value in fields.items()})
    return row


def upsert_slot_run(client: Any, row: dict[str, Any]) -> dict[str, Any]:
    """Read the tab once and use a full-row batch update instead of ws.find()."""
    from sheets_client import TAB_DEFINITIONS

    if getattr(client, "dry_run", False):
        return {"status": "PLAN_ONLY", "slot_run_id": row["slot_run_id"]}
    ws = client._ensure_tab("content_slot_runs", TAB_DEFINITIONS["content_slot_runs"])
    values = client._call_with_rate_limit_retry("get_all_values:content_slot_runs", ws.get_all_values)
    headers = values[0] if values else TAB_DEFINITIONS["content_slot_runs"]
    key_column = headers.index("slot_run_id") if "slot_run_id" in headers else -1
    row_number = next((index for index, item in enumerate(values[1:], start=2) if key_column >= 0 and len(item) > key_column and str(item[key_column]) == row["slot_run_id"]), 0)
    row["updated_at"] = datetime.now(timezone.utc).isoformat()
    values_to_write = [[str(row.get(header, "")) for header in headers]]
    if row_number:
        end_column = _column_letter(len(headers))
        client._call_with_rate_limit_retry(
            "batch_update:content_slot_runs",
            lambda: ws.batch_update([{"range": f"A{row_number}:{end_column}{row_number}", "values": values_to_write}], value_input_option="USER_ENTERED"),
        )
        return {"status": "UPDATED", "slot_run_id": row["slot_run_id"]}
    client._call_with_rate_limit_retry(
        "append_row:content_slot_runs",
        lambda: ws.append_row(values_to_write[0], value_input_option="USER_ENTERED"),
    )
    return {"status": "CREATED", "slot_run_id": row["slot_run_id"]}


def existing_slot_status(client: Any, account_id: str, slot_id: str, at: datetime | None = None) -> str:
    expected = slot_run_id(account_id, slot_id, at)
    try:
        rows = client._ws("content_slot_runs").get_all_records()
    except Exception:
        return ""
    for row in rows:
        if str(row.get("slot_run_id", "")) == expected:
            return str(row.get("status", ""))
    return ""


def _column_letter(column: int) -> str:
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters
