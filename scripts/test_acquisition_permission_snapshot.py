#!/usr/bin/env python3
"""Permission evidence is read once per bounded acquisition run."""

import acquire_approved_source_posts as acquisition


class Worksheet:
    def __init__(self, rows):
        self.rows = rows
        self.read_count = 0

    def get_all_records(self):
        self.read_count += 1
        return [dict(row) for row in self.rows]


class Client:
    def __init__(self, worksheet):
        self.worksheet = worksheet
        self.ensure_count = 0

    def _ensure_tab(self, logical, _headers):
        assert logical == "media_permissions"
        self.ensure_count += 1

    def _ws(self, logical):
        assert logical == "media_permissions"
        return self.worksheet

    def _call_with_rate_limit_retry(self, _label, fn):
        return fn()


def permission(source_id, account_id):
    return {
        "source_id": source_id,
        "source_handle": source_id,
        "account_id": account_id,
        "allowed_accounts": account_id,
        "permission_status": "approved",
        "rights_status": "owned",
        "usage_mode": "direct_media_reuse",
        "evidence_type": "owner_attested",
        "evidence_reference": f"evidence:{source_id}",
        "approved_by": "owner",
        "approved_at": "2026-01-01T00:00:00+00:00",
        "allow_download": "true",
        "allow_cloudinary_storage": "true",
        "allow_original_repost": "true",
        "allow_new_caption": "true",
    }


worksheet = Worksheet(
    [
        permission("source_one", "night_scout"),
        permission("source_two", "night_scout"),
    ]
)
client = Client(worksheet)

first = acquisition.ledger_permission(
    client,
    "source_one",
    account_id="night_scout",
    source_handle="source_one",
)
second = acquisition.ledger_permission(
    client,
    "source_two",
    account_id="night_scout",
    source_handle="source_two",
)
missing = acquisition.ledger_permission(
    client,
    "source_missing",
    account_id="night_scout",
    source_handle="source_missing",
)

assert first and first["source_id"] == "source_one"
assert second and second["source_id"] == "source_two"
assert missing is None
assert worksheet.read_count == 1
assert client.ensure_count == 1

print("[PASS] acquisition reuses one fail-closed permission ledger snapshot")
