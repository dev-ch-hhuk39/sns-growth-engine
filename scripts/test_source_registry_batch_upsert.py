#!/usr/bin/env python3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from recover_production_sheets_threads_first import _upsert_many


class Worksheet:
    def __init__(self):
        self.updated = []
        self.appended = []

    def row_values(self, row):
        assert row == 1
        return ["source_id", "source_name", "legacy_column"]

    def get_all_records(self):
        return [
            {"source_id": "s1", "source_name": "old", "legacy_column": "keep"},
            {"source_id": "legacy", "source_name": "legacy", "legacy_column": "untouched"},
        ]

    def update(self, values, start, **kwargs):
        self.updated.append((values, start, kwargs))

    def append_rows(self, values, **kwargs):
        self.appended.append((values, kwargs))


class Client:
    dry_run = False

    def __init__(self):
        self.ws = Worksheet()


client = Client()
client._recovery_ws_cache = {"source_accounts": client.ws}
result = _upsert_many(client, "source_accounts", "source_id", [
    {"source_id": "s1", "source_name": "new"},
    {"source_id": "s2", "source_name": "added"},
])

values = client.ws.updated[0][0]
checks = [
    result == {"added": 1, "updated": 1},
    len(client.ws.updated) == 1,
    client.ws.updated[0][1] == "A2",
    values[0] == ["s1", "new", "keep"],
    values[1] == ["legacy", "legacy", "untouched"],
    len(client.ws.appended) == 1,
    client.ws.appended[0][0][0] == ["s2", "added", ""],
]
print(f"PASS: {sum(checks)} / FAIL: {len(checks)-sum(checks)}")
raise SystemExit(0 if all(checks) else 1)
