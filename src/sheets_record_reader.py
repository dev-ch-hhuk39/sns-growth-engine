"""Blank-header-safe Google Sheets record reader."""

from __future__ import annotations

from typing import Any


READONLY_RECORD_CACHE_ATTR = "_readonly_sheet_record_cache"


def enable_readonly_record_cache(client: Any) -> None:
    """Enable an invocation-scoped Sheets snapshot for a read-only client."""

    setattr(client, READONLY_RECORD_CACHE_ATTR, {})


def _cached_records(
    client: Any,
    logical: str,
) -> list[dict[str, Any]] | None:
    cache = getattr(client, READONLY_RECORD_CACHE_ATTR, None)
    if not isinstance(cache, dict) or logical not in cache:
        return None
    return [dict(row) for row in cache[logical]]


def _store_cached_records(
    client: Any,
    logical: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    copied = [dict(row) for row in rows]
    cache = getattr(client, READONLY_RECORD_CACHE_ATTR, None)
    if isinstance(cache, dict):
        cache[logical] = [dict(row) for row in copied]
    return copied


def records_from_values(
    values: list[list[Any]],
) -> list[dict[str, Any]]:
    """Convert a Sheets values grid into records.

    Blank header cells are ignored. Duplicate nonblank headers remain
    fail-closed because they would make record identity ambiguous.
    """

    if not values:
        return []

    headers = [
        str(value or "")
        for value in values[0]
    ]

    nonempty_headers = [
        header
        for header in headers
        if header
    ]

    if len(nonempty_headers) != len(
        set(nonempty_headers)
    ):
        raise RuntimeError(
            "safe_sheet_records_duplicate_nonempty_headers"
        )

    records: list[dict[str, Any]] = []

    for raw_row in values[1:]:
        record = {
            header: (
                raw_row[index]
                if index < len(raw_row)
                else ""
            )
            for index, header
            in enumerate(headers)
            if header
        }

        if any(
            str(value or "").strip()
            for value in record.values()
        ):
            records.append(record)

    return records


def _is_duplicate_header_error(
    error: Exception,
) -> bool:
    message = str(error).lower()

    return (
        "header row" in message
        and "duplicate" in message
    )



def _call_with_optional_retry(
    client: Any,
    label: str,
    function: Any,
) -> Any:
    """Use the production retry wrapper when the client provides it."""

    retry = getattr(
        client,
        "_call_with_rate_limit_retry",
        None,
    )

    if callable(retry):
        return retry(
            label,
            function,
        )

    return function()


def read_records_safely(
    client: Any,
    logical: str,
) -> list[dict[str, Any]]:
    """Preserve get_all_records normally and recover blank headers safely."""

    cached = _cached_records(client, logical)
    if cached is not None:
        return cached

    worksheet = client._ws(logical)

    try:
        rows = _call_with_optional_retry(
            client,
            f"get_all_records:{logical}",
            worksheet.get_all_records,
        )

        return _store_cached_records(
            client,
            logical,
            [dict(row) for row in rows],
        )

    except Exception as error:
        if not _is_duplicate_header_error(
            error
        ):
            raise

    values = _call_with_optional_retry(
        client,
        f"get_all_values:{logical}:blank_header_fallback",
        worksheet.get_all_values,
    )

    return _store_cached_records(
        client,
        logical,
        records_from_values(list(values or [])),
    )
