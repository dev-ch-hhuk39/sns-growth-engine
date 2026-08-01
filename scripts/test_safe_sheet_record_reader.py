#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT / "src"),
)

from sheets_record_reader import (  # noqa: E402
    read_records_safely,
    records_from_values,
)


class Client:
    def __init__(self, worksheet):
        self.worksheet = worksheet
        self.labels = []

    def _ws(self, _logical):
        return self.worksheet

    def _call_with_rate_limit_retry(
        self,
        label,
        function,
    ):
        self.labels.append(label)
        return function()


class NormalWorksheet:
    def __init__(self):
        self.values_called = False

    def get_all_records(self):
        return [
            {
                "queue_id": "q-normal",
                "priority": 1,
            }
        ]

    def get_all_values(self):
        self.values_called = True
        raise AssertionError(
            "fallback must not run"
        )


class BlankHeaderWorksheet:
    def get_all_records(self):
        raise Exception(
            "the header row in the worksheet "
            "contains duplicates: ['']"
        )

    def get_all_values(self):
        return [
            [
                "queue_id",
                "",
                "status",
                "",
            ],
            [
                "q-safe",
                "ignored",
                "READY",
                "ignored",
            ],
        ]


normal = NormalWorksheet()

normal_rows = read_records_safely(
    Client(normal),
    "queue",
)

assert normal_rows == [
    {
        "queue_id": "q-normal",
        "priority": 1,
    }
]

assert normal.values_called is False

fallback_client = Client(
    BlankHeaderWorksheet()
)

fallback_rows = read_records_safely(
    fallback_client,
    "queue",
)

assert fallback_rows == [
    {
        "queue_id": "q-safe",
        "status": "READY",
    }
]

assert (
    "get_all_values:queue:"
    "blank_header_fallback"
    in fallback_client.labels
)

try:
    records_from_values([
        [
            "queue_id",
            "queue_id",
        ],
        [
            "q1",
            "q2",
        ],
    ])
except RuntimeError as error:
    assert str(error) == (
        "safe_sheet_records_"
        "duplicate_nonempty_headers"
    )
else:
    raise AssertionError(
        "duplicate nonblank headers must fail"
    )

print(
    "PASS: normal get_all_records behavior preserved"
)
print(
    "PASS: blank headers recover through raw values"
)
print(
    "PASS: duplicate nonblank headers remain blocked"
)
