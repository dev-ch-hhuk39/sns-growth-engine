#!/usr/bin/env python3
from __future__ import annotations

from generate_threads_ideas_from_references import (
    _append_missing,
)
from sheets_client import TAB_DEFINITIONS


required = {
    "drafts": {
        "transformation_type",
        "source_credit",
        "similarity_score",
        "direct_copy_guard",
    },
    "social_derivatives": {
        "transformation_type",
        "source_credit",
        "similarity_score",
    },
    "queue": {
        "transformation_type",
        "source_credit",
    },
}

for logical, fields in required.items():
    headers = set(
        TAB_DEFINITIONS[logical]
    )

    missing = fields - headers

    assert not missing, (
        logical,
        sorted(missing),
    )


class FakeWorksheet:
    def __init__(self) -> None:
        # Simulate the old Production queue schema.
        self.headers = [
            "queue_id",
            "draft_id",
            "account_id",
            "status",
            "content_route",
        ]

        self.appended = []
        self.batch_updates = []

    def row_values(
        self,
        row_number: int,
    ):
        assert row_number == 1
        return list(self.headers)

    def get_all_records(self):
        return []

    def append_rows(
        self,
        rows,
        value_input_option=None,
    ):
        self.appended.extend(rows)

    def batch_update(
        self,
        ranges,
        value_input_option=None,
    ):
        self.batch_updates.extend(ranges)


class FakeClient:
    def __init__(self) -> None:
        self.ws = FakeWorksheet()
        self.ensure_calls = []

    def _ensure_tab(
        self,
        logical,
        headers,
    ):
        self.ensure_calls.append(logical)

        for header in headers:
            if header not in self.ws.headers:
                self.ws.headers.append(header)

        return self.ws

    def _ws(self, logical):
        return self.ws


client = FakeClient()

result = _append_missing(
    client,
    "queue",
    "queue_id",
    [
        {
            "queue_id": "q_pdca_1",
            "draft_id": "d_pdca_1",
            "account_id": "night_scout",
            "status": "WAITING_REVIEW",
            "content_route": "pdca_text",
            "transformation_type": (
                "metrics_pdca_owned_post"
            ),
            "source_credit": (
                "owned_post_metrics"
            ),
        }
    ],
)

assert client.ensure_calls == ["queue"]

assert result == {
    "added": 1,
    "skipped": 0,
    "refreshed": 0,
}

assert len(client.ws.appended) == 1

written = dict(
    zip(
        client.ws.headers,
        client.ws.appended[0],
    )
)

assert (
    written["transformation_type"]
    == "metrics_pdca_owned_post"
)

assert (
    written["source_credit"]
    == "owned_post_metrics"
)

print(
    "PASS "
    "test_generation_provenance_schema_contract.py"
)
