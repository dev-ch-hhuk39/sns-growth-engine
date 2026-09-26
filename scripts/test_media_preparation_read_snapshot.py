#!/usr/bin/env python3
"""Media preparation reuses a single read-only batch snapshot."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import run_media_production_pipeline as pipeline  # noqa: E402
from sheets_record_reader import (  # noqa: E402
    READONLY_RECORD_CACHE_ATTR,
    enable_readonly_record_cache,
    prime_readonly_record_cache,
)


class Worksheet:
    def __init__(self, logical):
        self.title = logical
        self.row_count = 20
        self.col_count = 3
        self.created = False


class Spreadsheet:
    def __init__(self):
        self.calls = []

    def values_batch_get(self, ranges, params=None):
        self.calls.append((list(ranges), dict(params or {})))
        return {"valueRanges": [
            {"range": name, "values": [["record_id", "value"], [f"row-{index}", "ok"]]}
            for index, name in enumerate(ranges)
        ]}


class Client:
    def __init__(self):
        self._sh = Spreadsheet()
        self.tabs = {logical: Worksheet(logical) for logical in pipeline.MEDIA_PREPARATION_SNAPSHOT_LOGICALS}

    def _ws(self, logical):
        return self.tabs[logical]

    def _call_with_rate_limit_retry(self, _name, fn):
        return fn()

    def _ensure_tab(self, logical, _definition):
        self.tabs[logical].created = True


client = Client()
enable_readonly_record_cache(client)
prime_readonly_record_cache(client, pipeline.MEDIA_PREPARATION_SNAPSHOT_LOGICALS)
assert len(client._sh.calls) == 1
assert len(client._sh.calls[0][0]) == len(pipeline.MEDIA_PREPARATION_SNAPSHOT_LOGICALS)
assert all(value.endswith("!A1:C20") for value in client._sh.calls[0][0])
assert all(not row.created for row in client.tabs.values())
assert pipeline._records(client, "source_videos") == [{"record_id": f"row-{pipeline.MEDIA_PREPARATION_SNAPSHOT_LOGICALS.index('source_videos')}", "value": "ok"}]
assert pipeline._records(client, "media_permissions") == [{"record_id": f"row-{pipeline.MEDIA_PREPARATION_SNAPSHOT_LOGICALS.index('media_permissions')}", "value": "ok"}]
assert len(client._sh.calls) == 1
assert len(getattr(client, READONLY_RECORD_CACHE_ATTR)) == len(pipeline.MEDIA_PREPARATION_SNAPSHOT_LOGICALS)
print("PASS test_media_preparation_read_snapshot.py")
