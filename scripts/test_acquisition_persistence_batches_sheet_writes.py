#!/usr/bin/env python3
"""Acquisition persistence stays deduplicated while using bounded Sheets writes."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import acquire_approved_source_posts as acquisition  # noqa: E402
from acquisition.models import NormalizedMediaItem, NormalizedSourcePost  # noqa: E402


class Worksheet:
    def __init__(self, headers, rows=()):
        self.headers = list(headers)
        self.rows = [dict(row) for row in rows]
        self.append_rows_calls = []

    def row_values(self, _row):
        return list(self.headers)

    def get_all_records(self):
        return [dict(row) for row in self.rows]

    def append_rows(self, values, value_input_option="USER_ENTERED"):
        assert value_input_option == "USER_ENTERED"
        self.append_rows_calls.append(values)
        self.rows.extend(dict(zip(self.headers, row)) for row in values)

    def append_row(self, *_args, **_kwargs):
        raise AssertionError("acquisition persistence must not append one row per request")


class Client:
    def __init__(self, sheets):
        self.sheets = sheets

    def _ensure_tab(self, logical, _headers):
        return self.sheets[logical]

    def _call_with_rate_limit_retry(self, _label, callback):
        return callback()


post_url = "https://www.youtube.com/watch?v=video123456"
post_id = "sp_source_video123456"
post = NormalizedSourcePost(
    source_post_id=post_id,
    source_id="source",
    target_account_id="night_scout",
    platform="youtube",
    profile_url="https://www.youtube.com/@source",
    canonical_post_url=post_url,
    external_post_id="video123456",
    original_post_text="bounded acquisition",
    published_at="2026-08-25T00:00:00Z",
    media_items=(
        NormalizedMediaItem(
            source_post_media_id=f"spm_{post_id}_0",
            source_post_id=post_id,
            media_index=0,
            media_type="video",
            canonical_post_url=post_url,
            original_media_url=post_url,
            resolver_backend="youtube_public_html",
        ),
    ),
    collection_backend="youtube_public_html",
    backend_version="1",
    content_hash="content-hash",
    discovered_at="2026-08-25T00:00:00Z",
)

sheets = {
    "source_posts": Worksheet(["source_post_id", "canonical_post_url"]),
    "source_post_media": Worksheet(
        ["source_post_media_id", "source_post_id", "media_index", "original_media_url"]
    ),
    "provider_runs": Worksheet(["provider_run_id", "source_id"]),
}
client = Client(sheets)

result = acquisition.persist(client, [post, post])
assert result["saved_source_posts"] == 1
assert result["saved_source_post_media"] == 1
assert result["duplicate_source_posts"] == 1
assert len(sheets["source_posts"].append_rows_calls) == 1
assert len(sheets["source_post_media"].append_rows_calls) == 1
assert len(sheets["source_posts"].append_rows_calls[0]) == 1
assert len(sheets["source_post_media"].append_rows_calls[0]) == 1

saved = acquisition.persist_auxiliary(
    client,
    "provider_runs",
    [
        {"provider_run_id": "run-1", "source_id": "source"},
        {"provider_run_id": "run-1", "source_id": "source"},
        {"provider_run_id": "run-2", "source_id": "source"},
    ],
    identity_fields=("provider_run_id",),
)
assert saved == 2
assert len(sheets["provider_runs"].append_rows_calls) == 1
assert len(sheets["provider_runs"].append_rows_calls[0]) == 2

print("PASS test_acquisition_persistence_batches_sheet_writes.py")
