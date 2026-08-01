#!/usr/bin/env python3

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path[:0] = [
    str(ROOT / "scripts"),
    str(ROOT / "src"),
]

import run_direct_reference_media_pipeline_batched as module


class FakeWorksheet:
    def __init__(self, title: str):
        self.title = title
        self.row_count = 100
        self.col_count = 10


class FakeSpreadsheet:
    def __init__(self):
        self.calls = []

    def values_batch_get(self, ranges, params=None):
        self.calls.append(
            {
                "ranges": list(ranges),
                "params": dict(params or {}),
            }
        )

        return {
            "valueRanges": [
                {
                    "range": range_name,
                    "values": [
                        [
                            "record_id",
                            "value",
                        ],
                        [
                            f"{logical}-1",
                            "ok",
                        ],
                    ],
                }
                for logical, range_name in zip(
                    module.SNAPSHOT_LOGICALS,
                    ranges,
                    strict=True,
                )
            ]
        }


class FakeClient:
    def __init__(self):
        self._sh = FakeSpreadsheet()
        self._direct_media_records_cache = {}
        self.worksheets = {
            logical: FakeWorksheet(
                f"sheet-{logical}"
            )
            for logical in module.SNAPSHOT_LOGICALS
        }

    def _ws(self, logical):
        return self.worksheets[logical]

    def _call_with_rate_limit_retry(
        self,
        _label,
        fn,
    ):
        return fn()


client = FakeClient()

source_posts = module._batched_records(
    client,
    "source_posts",
)

assert source_posts == [
    {
        "record_id": "source_posts-1",
        "value": "ok",
    }
]

assert len(client._sh.calls) == 1
assert len(
    client._sh.calls[0]["ranges"]
) == len(module.SNAPSHOT_LOGICALS)

assert (
    client._sh.calls[0]["params"][
        "majorDimension"
    ]
    == "ROWS"
)

assert (
    client._sh.calls[0]["params"][
        "valueRenderOption"
    ]
    == "FORMATTED_VALUE"
)

media_assets = module._batched_records(
    client,
    "media_assets",
)

assert media_assets[0]["record_id"] == "media_assets-1"
assert len(client._sh.calls) == 1

client._direct_media_records_cache.pop(
    "queue"
)

queue = module._batched_records(
    client,
    "queue",
)

assert queue[0]["record_id"] == "queue-1"
assert len(client._sh.calls) == 2

original = module._ORIGINAL_RECORDS

try:
    module._ORIGINAL_RECORDS = (
        lambda _client, logical: [
            {
                "logical": logical,
            }
        ]
    )

    assert module._batched_records(
        client,
        "non_snapshot_tab",
    ) == [
        {
            "logical": "non_snapshot_tab",
        }
    ]

finally:
    module._ORIGINAL_RECORDS = original

print(
    "PASS "
    "test_direct_media_batch_snapshot.py"
)
