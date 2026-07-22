#!/usr/bin/env python3
"""Idempotent Sheets persistence for scheduled content slots."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from content_schedule import slot_by_id

JST = timezone(timedelta(hours=9))


def now_jst() -> datetime:
    return datetime.now(JST)


def business_date(at: datetime | None = None) -> str:
    """Return the JST operational date, which rolls over at 04:00.

    The 25:00 slot executes at 01:00 on the following calendar day but belongs
    to the prior business date.  Every caller should use this resolver instead
    of deriving a date from a wall-clock hour.
    """
    local = (at or now_jst()).astimezone(JST)
    if local.hour < 4:
        local -= timedelta(days=1)
    return local.strftime("%Y-%m-%d")


def slot_run_id(account_id: str, slot_id: str, at: datetime | None = None) -> str:
    date = business_date(at).replace("-", "")
    return f"slot_{date}_{account_id}_{slot_id}"


def posts_used_in_business_date(account_id: str, rows: list[dict[str, Any]], at: datetime | None = None) -> int:
    """Count posted Threads rows using the same 04:00 JST boundary as slots."""
    target = business_date(at)
    count = 0
    for row in rows:
        if str(row.get("account_id", "")) != account_id:
            continue
        if str(row.get("platform", "")).lower() not in {"", "threads"}:
            continue
        if str(row.get("status", "")).upper() not in {"", "POSTED", "RECOVERED"}:
            continue
        raw = str(row.get("posted_at") or row.get("created_at") or row.get("collected_at") or "")
        try:
            posted = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if business_date(posted) == target:
            count += 1
    return count


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
    schedule_date = datetime.fromisoformat(business_date(local)).date()
    target_date = schedule_date
    target_hour, target_minute = map(int, str(slot["target_jst"]).split(":"))
    if target_hour >= 24:
        target_hour -= 24
        target_date += timedelta(days=1)
    target = datetime(target_date.year, target_date.month, target_date.day, target_hour, target_minute, tzinfo=JST)
    created = local.isoformat()
    row = {
        "slot_run_id": slot_run_id(account_id, slot_id, local),
        "schedule_date_jst": business_date(local),
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
        "idempotency_key": slot_run_id(account_id, slot_id, local),
        "claim_status": "",
        "lease_expires_at": "",
        "publish_attempt_id": "",
        "actual_generation_mode": "",
        "metrics_result_id": "",
        "created_at": created,
        "updated_at": created,
    }
    row.update({key: "" if value is None else str(value) for key, value in fields.items()})
    return row


def _slot_run_contract_issues(existing: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    """Return contract fields that failed persistence read-after-write."""
    required = ("slot_run_id", "schedule_date_jst", "account_id", "slot_id", "idempotency_key")
    return [
        field for field in required
        if str(existing.get(field, "")).strip() != str(expected.get(field, "")).strip()
    ]


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
        result = {"status": "UPDATED", "slot_run_id": row["slot_run_id"]}
    else:
        client._call_with_rate_limit_retry(
            "append_row:content_slot_runs",
            lambda: ws.append_row(values_to_write[0], value_input_option="USER_ENTERED"),
        )
        result = {"status": "CREATED", "slot_run_id": row["slot_run_id"]}
    verified = client._call_with_rate_limit_retry(
        "get_all_records:content_slot_runs:verify",
        lambda: ws.get_all_records(),
    )
    stored = next((item for item in verified if str(item.get("slot_run_id", "")) == row["slot_run_id"]), None)
    if not stored or _slot_run_contract_issues(stored, row):
        raise RuntimeError("content_slot_run_read_after_write_failed")
    return result


def existing_slot_row(client: Any, account_id: str, slot_id: str, at: datetime | None = None) -> dict[str, Any] | None:
    expected = slot_run_id(account_id, slot_id, at)
    try:
        from sheets_client import TAB_DEFINITIONS
        ws = client._ensure_tab("content_slot_runs", TAB_DEFINITIONS["content_slot_runs"])
        rows = client._call_with_rate_limit_retry(
            "get_all_records:content_slot_runs:existing",
            lambda: ws.get_all_records(),
        )
    except Exception:
        return None
    for row in rows:
        if str(row.get("slot_run_id", "")) == expected:
            return dict(row)
    return None


def existing_slot_status(client: Any, account_id: str, slot_id: str, at: datetime | None = None) -> str:
    row = existing_slot_row(client, account_id, slot_id, at)
    return str((row or {}).get("status", ""))


def claim_slot_run(
    client: Any,
    account_id: str,
    slot_id: str,
    *,
    at: datetime | None = None,
    lease_minutes: int = 45,
) -> dict[str, Any]:
    """Claim a business-date slot or return a safe duplicate/lease outcome.

    Sheets has no compare-and-swap primitive, so the deterministic row is
    written before any publisher call and is rechecked by every workflow. This
    prevents normal concurrent runners from publishing the same slot twice;
    expired claims are intentionally recoverable.
    """
    local = (at or now_jst()).astimezone(JST)
    expected = slot_run_id(account_id, slot_id, local)
    try:
        from sheets_client import TAB_DEFINITIONS
        ws = client._ensure_tab("content_slot_runs", TAB_DEFINITIONS["content_slot_runs"])
        rows = client._call_with_rate_limit_retry(
            "get_all_records:content_slot_runs:claim",
            lambda: ws.get_all_records(),
        )
    except Exception as exc:
        return {"status": "BLOCKED", "reason": f"slot_claim_read_failed:{type(exc).__name__}", "slot_run_id": expected}
    for existing in rows:
        if str(existing.get("slot_run_id", "")) != expected:
            continue
        status = str(existing.get("status", ""))
        if status in {"POSTED_PRIMARY", "POSTED_FALLBACK", "BACKFILLED", "POSTED"}:
            return {"status": "SKIPPED", "reason": "slot_already_posted", "slot_run_id": expected}
        if status == "RECOVERY_REQUIRED":
            # A stale execution must be reconciled explicitly.  Taking a new
            # claim here could publish the same business-date slot twice.
            return {"status": "SKIPPED", "reason": "slot_recovery_required", "slot_run_id": expected}
        expiry = str(existing.get("lease_expires_at", ""))
        if str(existing.get("claim_status", "")) == "CLAIMED" and expiry:
            try:
                if datetime.fromisoformat(expiry).astimezone(JST) > local:
                    return {"status": "SKIPPED", "reason": "slot_lease_active", "slot_run_id": expected}
            except ValueError:
                return {"status": "SKIPPED", "reason": "slot_lease_invalid", "slot_run_id": expected}
    row = build_slot_run(account_id, slot_id, status="CLAIMED", now=local)
    row.update({
        "claim_status": "CLAIMED",
        "lease_expires_at": (local + timedelta(minutes=lease_minutes)).isoformat(),
        "publish_attempt_id": f"attempt_{local.strftime('%Y%m%dT%H%M%S')}",
    })
    saved = upsert_slot_run(client, row)
    return {"status": "CLAIMED" if saved.get("status") in {"CREATED", "UPDATED"} else "BLOCKED", "slot_run_id": expected, "save": saved}


def _column_letter(column: int) -> str:
    letters = ""
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters
