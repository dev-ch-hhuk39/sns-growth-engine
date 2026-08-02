#!/usr/bin/env python3
"""Contract tests for the route-provenance Sheets schema guard."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

from ensure_route_provenance_schema import (
    TARGET_COLUMNS,
    ensure,
    inspect,
)
from sheets_client import TAB_DEFINITIONS


class FakeWorksheet:
    def __init__(
        self,
        headers: list[str],
    ) -> None:
        self.headers = list(headers)
        self.col_count = max(
            len(self.headers),
            1,
        )
        self.row_count = 100
        self.resize_calls: list[
            dict[str, int]
        ] = []
        self.update_calls: list[
            dict[str, Any]
        ] = []

    def row_values(
        self,
        row: int,
    ) -> list[str]:
        assert row == 1
        return list(self.headers)

    def resize(
        self,
        *,
        rows: int,
        cols: int,
    ) -> None:
        self.row_count = rows
        self.col_count = cols
        self.resize_calls.append({
            "rows": rows,
            "cols": cols,
        })

    def update(
        self,
        values: list[list[str]],
        range_name: str,
        *,
        major_dimension: str,
    ) -> None:
        assert major_dimension == "COLUMNS"

        appended = [
            row[0]
            for row in values
        ]

        self.headers.extend(appended)

        self.update_calls.append({
            "values": values,
            "range": range_name,
            "major_dimension": (
                major_dimension
            ),
        })


class FakeClient:
    def __init__(
        self,
        tabs: dict[str, FakeWorksheet],
    ) -> None:
        self.tabs = dict(tabs)
        self.retry_labels: list[str] = []

    def _ws(
        self,
        logical_name: str,
    ) -> FakeWorksheet:
        if logical_name not in self.tabs:
            raise KeyError(logical_name)

        return self.tabs[logical_name]

    def _call_with_rate_limit_retry(
        self,
        label: str,
        fn: Any,
    ) -> Any:
        self.retry_labels.append(label)
        return fn()


required = (
    "content_route",
    "source_content_route",
    "source_generation_mode",
    "source_result_id",
)

assert set(TARGET_COLUMNS) == {
    "drafts",
    "queue",
    "posted_results",
}

for logical_name in TARGET_COLUMNS:
    assert TARGET_COLUMNS[logical_name] == required

    for column in required:
        assert (
            column
            in TAB_DEFINITIONS[logical_name]
        )


base_headers = {
    logical_name: [
        "id",
        "created_at",
        "account_id",
    ]
    for logical_name in TARGET_COLUMNS
}

audit_client = FakeClient({
    logical_name: FakeWorksheet(headers)
    for logical_name, headers
    in base_headers.items()
})

audit = inspect(audit_client)

assert audit["status"] == "SCHEMA_MISSING"
assert audit["would_write"] is False
assert audit["would_delete"] is False
assert audit["would_reorder"] is False
assert audit["would_create_tab"] is False
assert audit["would_post"] is False

for logical_name in TARGET_COLUMNS:
    assert (
        audit["tabs"][logical_name][
            "missing_columns"
        ]
        == list(required)
    )

apply_client = FakeClient({
    logical_name: FakeWorksheet(headers)
    for logical_name, headers
    in base_headers.items()
})

before_headers = {
    logical_name: list(ws.headers)
    for logical_name, ws
    in apply_client.tabs.items()
}

applied = ensure(apply_client)

assert applied["status"] == "APPLIED"
assert applied["would_write"] is True
assert applied["would_delete"] is False
assert applied["would_reorder"] is False
assert applied["would_create_tab"] is False
assert applied["would_post"] is False
assert set(applied["changed_tabs"]) == {
    "drafts",
    "queue",
    "posted_results",
}

for logical_name, ws in (
    apply_client.tabs.items()
):
    assert (
        ws.headers[:len(
            before_headers[logical_name]
        )]
        == before_headers[logical_name]
    )

    assert (
        ws.headers[
            len(before_headers[logical_name]):
        ]
        == list(required)
    )

    assert len(ws.update_calls) == 1


missing_tab_client = FakeClient({
    "drafts": FakeWorksheet(
        base_headers["drafts"]
    ),
    "queue": FakeWorksheet(
        base_headers["queue"]
    ),
})

missing_tab_result = ensure(
    missing_tab_client
)

assert (
    missing_tab_result["status"]
    == "BLOCKED_MISSING_TAB"
)

assert missing_tab_result["would_write"] is False
assert (
    missing_tab_result["would_create_tab"]
    is False
)

for ws in missing_tab_client.tabs.values():
    assert ws.update_calls == []


duplicate_client = FakeClient({
    logical_name: FakeWorksheet(
        (
            headers
            + ["content_route"]
            + ["content_route"]
        )
        if logical_name == "queue"
        else headers
    )
    for logical_name, headers
    in base_headers.items()
})

duplicate_result = ensure(
    duplicate_client
)

assert (
    duplicate_result["status"]
    == "BLOCKED_DUPLICATE_HEADERS"
)

assert duplicate_result["would_write"] is False

for ws in duplicate_client.tabs.values():
    assert ws.update_calls == []


script = (
    ROOT
    / "scripts"
    / "ensure_route_provenance_schema.py"
)

blocked_no_sheets = subprocess.run(
    [
        sys.executable,
        str(script),
        "--dry-run",
    ],
    cwd=ROOT,
    text=True,
    capture_output=True,
)

assert blocked_no_sheets.returncode == 1
assert "--use-sheets is required" in (
    blocked_no_sheets.stdout
)

blocked_no_confirm = subprocess.run(
    [
        sys.executable,
        str(script),
        "--use-sheets",
        "--apply",
    ],
    cwd=ROOT,
    text=True,
    capture_output=True,
)

assert blocked_no_confirm.returncode == 1
assert (
    "--apply requires "
    "--confirm-route-schema"
    in blocked_no_confirm.stdout
)

source = script.read_text(
    encoding="utf-8",
)

import ast

tree = ast.parse(source)

called_names: set[str] = set()

for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue

    if isinstance(node.func, ast.Name):
        called_names.add(node.func.id)

    elif isinstance(node.func, ast.Attribute):
        called_names.add(node.func.attr)

forbidden_calls = {
    "append_row",
    "append_rows",
    "add_worksheet",
    "setup_all",
    "delete",
    "delete_row",
    "delete_rows",
    "delete_column",
    "delete_columns",
    "batch_clear",
    "clear",
}

unexpected_calls = sorted(
    forbidden_calls & called_names
)

assert unexpected_calls == [], unexpected_calls

assert "publisher" not in source.lower()
assert "post_to_" not in source

print(
    "PASS "
    "test_route_provenance_schema_guard.py"
)
