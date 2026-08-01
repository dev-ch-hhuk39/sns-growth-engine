"""Blank-header-safe Google Sheets record reader."""

from __future__ import annotations

from typing import Any


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

    worksheet = client._ws(logical)

    try:
        rows = _call_with_optional_retry(
            client,
            f"get_all_records:{logical}",
            worksheet.get_all_records,
        )

        return [
            dict(row)
            for row in rows
        ]

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

    return records_from_values(
        list(values or [])
    )
