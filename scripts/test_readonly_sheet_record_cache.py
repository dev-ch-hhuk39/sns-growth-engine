#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sheets_record_reader import enable_readonly_record_cache, read_records_safely  # noqa: E402


class Worksheet:
    def __init__(self, rows):
        self.rows = [dict(row) for row in rows]
        self.calls = 0

    def get_all_records(self):
        self.calls += 1
        return [dict(row) for row in self.rows]


class Client:
    def __init__(self, rows):
        self.worksheet = Worksheet(rows)

    def _ws(self, logical):
        assert logical == "example"
        return self.worksheet

    def _call_with_rate_limit_retry(self, label, function):
        assert label == "get_all_records:example"
        return function()


client = Client([{"id": "1", "value": "original"}])
enable_readonly_record_cache(client)
first = read_records_safely(client, "example")
first[0]["value"] = "mutated-by-caller"
second = read_records_safely(client, "example")
assert client.worksheet.calls == 1, client.worksheet.calls
assert second == [{"id": "1", "value": "original"}], second

empty_client = Client([])
enable_readonly_record_cache(empty_client)
assert read_records_safely(empty_client, "example") == []
assert read_records_safely(empty_client, "example") == []
assert empty_client.worksheet.calls == 1, empty_client.worksheet.calls

uncached_client = Client([{"id": "2"}])
assert read_records_safely(uncached_client, "example") == [{"id": "2"}]
assert read_records_safely(uncached_client, "example") == [{"id": "2"}]
assert uncached_client.worksheet.calls == 2, uncached_client.worksheet.calls

print("PASS test_readonly_sheet_record_cache.py")
