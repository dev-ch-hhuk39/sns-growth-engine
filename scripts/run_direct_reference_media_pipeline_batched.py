#!/usr/bin/env python3
"""Run direct-media preparation with one bounded multi-tab Sheets read."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import run_direct_reference_media_pipeline as core
from sheets_record_reader import records_from_values


SNAPSHOT_LOGICALS = (
    "posted_results",
    "source_posts",
    "source_accounts",
    "reference_sources",
    "media_permissions",
    "queue",
    "media_assets",
    "source_post_media",
    "source_media_understanding",
    "quarantined_items",
)

_ORIGINAL_RECORDS = core._records
_ORIGINAL_NORMALIZE_PREPARE_ONLY = (
    core.normalize_prepare_only_outcome
)


def _col_letter(index: int) -> str:
    result = ""

    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result

    return result or "A"


def _sheet_range(worksheet: Any) -> str:
    title = str(worksheet.title).replace("'", "''")
    row_count = max(int(getattr(worksheet, "row_count", 1000) or 1000), 1)
    col_count = max(int(getattr(worksheet, "col_count", 1) or 1), 1)

    return f"'{title}'!A1:{_col_letter(col_count)}{row_count}"


def _records_from_values(
    values: list[list[Any]],
) -> list[dict[str, Any]]:
    return records_from_values(values)



def _prime_snapshot(client: Any, *, force: bool = False) -> None:
    loaded = bool(
        getattr(
            client,
            "_direct_media_batch_snapshot_loaded",
            False,
        )
    )

    if loaded and not force:
        return

    worksheets = [
        (
            logical,
            client._ws(logical),
        )
        for logical in SNAPSHOT_LOGICALS
    ]

    ranges = [
        _sheet_range(worksheet)
        for _logical, worksheet in worksheets
    ]

    payload = client._call_with_rate_limit_retry(
        "values_batch_get:direct_media_snapshot",
        lambda: client._sh.values_batch_get(
            ranges,
            params={
                "majorDimension": "ROWS",
                "valueRenderOption": "FORMATTED_VALUE",
            },
        ),
    )

    value_ranges = list(payload.get("valueRanges") or [])

    if len(value_ranges) != len(worksheets):
        raise RuntimeError(
            "direct_media_batch_snapshot_range_count_mismatch"
        )

    cache = getattr(
        client,
        "_direct_media_records_cache",
        None,
    )

    if not isinstance(cache, dict):
        cache = {}

    for (
        logical,
        _worksheet,
    ), value_range in zip(
        worksheets,
        value_ranges,
        strict=True,
    ):
        cache[logical] = _records_from_values(
            list(value_range.get("values") or [])
        )

    client._direct_media_records_cache = cache
    client._direct_media_batch_snapshot_loaded = True


def _batched_records(
    client: Any,
    logical: str,
) -> list[dict[str, Any]]:
    if logical not in SNAPSHOT_LOGICALS:
        return _ORIGINAL_RECORDS(
            client,
            logical,
        )

    cache = getattr(
        client,
        "_direct_media_records_cache",
        None,
    )

    if not isinstance(cache, dict) or logical not in cache:
        _prime_snapshot(
            client,
            force=bool(
                getattr(
                    client,
                    "_direct_media_batch_snapshot_loaded",
                    False,
                )
            ),
        )

        cache = getattr(
            client,
            "_direct_media_records_cache",
            {},
        )

    return [
        dict(row)
        for row in cache.get(
            logical,
            [],
        )
    ]


def _require_prepared_enabled() -> bool:
    return str(
        os.environ.get(
            "REQUIRE_PREPARED",
            "",
        )
    ).strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _normalize_prepare_only_outcome(
    plan: dict[str, Any],
    *,
    prepare_only: bool,
) -> dict[str, Any]:
    result = _ORIGINAL_NORMALIZE_PREPARE_ONLY(
        plan,
        prepare_only=prepare_only,
    )

    if (
        prepare_only
        and _require_prepared_enabled()
        and str(result.get("status", "")) != "PREPARED"
    ):
        prior_status = str(
            result.get("preparation_status")
            or result.get("status")
            or "UNKNOWN"
        )

        blocked_reasons = list(
            result.get("blocked_reasons")
            or []
        )

        blocked_reasons.append(
            "confirmed_preparation_did_not_create_ready_inventory"
        )

        return {
            **result,
            "status": "FAILED_READY_REQUIRED",
            "preparation_status": prior_status,
            "blocked_reasons": blocked_reasons[:30],
            "would_post": False,
        }

    return result


core._records = _batched_records
core.normalize_prepare_only_outcome = (
    _normalize_prepare_only_outcome
)


if __name__ == "__main__":
    raise SystemExit(core.main())
