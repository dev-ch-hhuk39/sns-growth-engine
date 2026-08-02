#!/usr/bin/env python3
"""Audit or append route-provenance columns on existing Sheets tabs.

This command is fail-closed:

- It only targets drafts, queue, and posted_results.
- Dry-run reads headers but never writes.
- Apply requires all three explicit flags:
  --use-sheets --apply --confirm-route-schema
- Missing tabs are never created.
- Existing columns are never deleted, reordered, or overwritten.
- Only missing route-provenance headers are appended to the right.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

TARGET_COLUMNS: dict[str, tuple[str, ...]] = {
    "drafts": (
        "content_route",
        "source_content_route",
        "source_generation_mode",
        "source_result_id",
    ),
    "queue": (
        "content_route",
        "source_content_route",
        "source_generation_mode",
        "source_result_id",
    ),
    "posted_results": (
        "content_route",
        "source_content_route",
        "source_generation_mode",
        "source_result_id",
    ),
}


def _read_headers(
    client: Any,
    logical_name: str,
) -> tuple[Any, list[str]]:
    ws = client._ws(logical_name)

    if hasattr(
        client,
        "_call_with_rate_limit_retry",
    ):
        headers = client._call_with_rate_limit_retry(
            f"read_route_headers:{logical_name}",
            lambda: ws.row_values(1),
        )
    else:
        headers = ws.row_values(1)

    return ws, [
        str(value).strip()
        for value in headers
    ]


def _duplicate_headers(
    headers: list[str],
) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []

    for header in headers:
        if not header:
            continue

        if (
            header in seen
            and header not in duplicates
        ):
            duplicates.append(header)

        seen.add(header)

    return duplicates


def inspect(
    client: Any,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "status": "SCHEMA_MISSING",
        "tabs": {},
        "target_columns": {
            logical: list(columns)
            for logical, columns
            in TARGET_COLUMNS.items()
        },
        "would_write": False,
        "would_delete": False,
        "would_reorder": False,
        "would_create_tab": False,
        "would_post": False,
    }

    for logical_name, required in (
        TARGET_COLUMNS.items()
    ):
        try:
            _ws, headers = _read_headers(
                client,
                logical_name,
            )
        except Exception as exc:
            report["tabs"][logical_name] = {
                "exists": False,
                "header_count": 0,
                "missing_columns": list(required),
                "duplicate_headers": [],
                "reason": type(exc).__name__,
            }
            continue

        report["tabs"][logical_name] = {
            "exists": True,
            "header_count": len(headers),
            "missing_columns": [
                column
                for column in required
                if column not in headers
            ],
            "duplicate_headers": (
                _duplicate_headers(headers)
            ),
        }

    tabs = list(report["tabs"].values())

    all_exist = all(
        tab.get("exists") is True
        for tab in tabs
    )

    no_missing = all(
        not tab.get("missing_columns")
        for tab in tabs
    )

    no_duplicates = all(
        not tab.get("duplicate_headers")
        for tab in tabs
    )

    if (
        all_exist
        and no_missing
        and no_duplicates
    ):
        report["status"] = "READ_OK"

    return report


def _append_missing_columns(
    client: Any,
    logical_name: str,
    missing: list[str],
) -> None:
    if not missing:
        return

    ws, existing = _read_headers(
        client,
        logical_name,
    )

    next_col = len(existing) + 1
    required_cols = len(existing) + len(missing)
    current_cols = int(
        getattr(
            ws,
            "col_count",
            required_cols,
        )
    )

    if required_cols > current_cols:
        new_cols = max(
            required_cols + 10,
            current_cols + 20,
        )

        client._call_with_rate_limit_retry(
            f"resize_route_headers:{logical_name}",
            lambda: ws.resize(
                rows=ws.row_count,
                cols=new_cols,
            ),
        )

    from sheets_client import _col_letter

    column_letter = _col_letter(next_col)

    client._call_with_rate_limit_retry(
        f"append_route_headers:{logical_name}",
        lambda: ws.update(
            [
                [column]
                for column in missing
            ],
            f"{column_letter}1",
            major_dimension="COLUMNS",
        ),
    )


def ensure(
    client: Any,
) -> dict[str, Any]:
    before = inspect(client)

    missing_tabs = [
        logical_name
        for logical_name, tab
        in before["tabs"].items()
        if not tab.get("exists")
    ]

    if missing_tabs:
        return {
            "status": "BLOCKED_MISSING_TAB",
            "missing_tabs": missing_tabs,
            "before": before,
            "would_write": False,
            "would_delete": False,
            "would_reorder": False,
            "would_create_tab": False,
            "would_post": False,
        }

    duplicate_headers = {
        logical_name: tab[
            "duplicate_headers"
        ]
        for logical_name, tab
        in before["tabs"].items()
        if tab.get("duplicate_headers")
    }

    if duplicate_headers:
        return {
            "status": (
                "BLOCKED_DUPLICATE_HEADERS"
            ),
            "duplicate_headers": (
                duplicate_headers
            ),
            "before": before,
            "would_write": False,
            "would_delete": False,
            "would_reorder": False,
            "would_create_tab": False,
            "would_post": False,
        }

    for logical_name in TARGET_COLUMNS:
        missing = list(
            before["tabs"][logical_name][
                "missing_columns"
            ]
        )

        _append_missing_columns(
            client,
            logical_name,
            missing,
        )

    after = inspect(client)

    status = (
        "APPLIED"
        if after["status"] == "READ_OK"
        else "PARTIAL_FAILURE"
    )

    changed_tabs = [
        logical_name
        for logical_name, tab
        in before["tabs"].items()
        if tab["missing_columns"]
    ]

    return {
        "status": status,
        "changed_tabs": changed_tabs,
        "before": before,
        "read_after_write": after,
        "would_write": bool(changed_tabs),
        "would_delete": False,
        "would_reorder": False,
        "would_create_tab": False,
        "would_post": False,
    }


def _make_real_client(
    *,
    dry_run: bool,
) -> Any:
    sys.path.insert(
        0,
        str(ROOT / "src"),
    )

    from config_loader import get_config
    from sheets_client import SheetsClient

    cfg = get_config()

    return SheetsClient(
        cfg["sheet_id"],
        cfg["sa_dict"],
        dry_run=dry_run,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    parser.add_argument(
        "--use-sheets",
        action="store_true",
        help=(
            "Use the configured Google Sheet. "
            "Required for both audit and apply."
        ),
    )

    mode = parser.add_mutually_exclusive_group(
        required=True,
    )

    mode.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Read the three header rows and "
            "report missing columns without writing."
        ),
    )

    mode.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Append only missing route columns."
        ),
    )

    parser.add_argument(
        "--confirm-route-schema",
        action="store_true",
        help=(
            "Required together with --apply."
        ),
    )

    args = parser.parse_args()

    if not args.use_sheets:
        print(json.dumps(
            {
                "status": "BLOCKED",
                "reason": (
                    "--use-sheets is required"
                ),
                "would_write": False,
                "would_post": False,
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 1

    if (
        args.apply
        and not args.confirm_route_schema
    ):
        print(json.dumps(
            {
                "status": "BLOCKED",
                "reason": (
                    "--apply requires "
                    "--confirm-route-schema"
                ),
                "would_write": False,
                "would_post": False,
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 1

    try:
        client = _make_real_client(
            dry_run=args.dry_run,
        )

        result = (
            ensure(client)
            if args.apply
            else inspect(client)
        )
    except Exception as exc:
        result = {
            "status": type(exc).__name__,
            "reason": (
                "Sheets configuration or "
                "read failed"
            ),
            "would_write": False,
            "would_delete": False,
            "would_reorder": False,
            "would_create_tab": False,
            "would_post": False,
        }

    print(json.dumps(
        result,
        ensure_ascii=False,
        indent=2,
    ))

    accepted = {
        "READ_OK",
        "APPLIED",
        "SCHEMA_MISSING",
    }

    return (
        0
        if result.get("status") in accepted
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
