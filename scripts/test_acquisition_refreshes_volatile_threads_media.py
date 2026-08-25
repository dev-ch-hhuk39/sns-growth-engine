#!/usr/bin/env python3
"""Duplicate discovery refreshes only the identical Threads media child."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import acquire_approved_source_posts as acquisition  # noqa: E402
from acquisition.models import NormalizedMediaItem, NormalizedSourcePost  # noqa: E402


class Worksheet:
    def __init__(self, headers, rows):
        self.headers = list(headers)
        self.rows = [dict(row) for row in rows]

    def row_values(self, _row):
        return self.headers

    def get_all_records(self):
        return [dict(row) for row in self.rows]

    def append_row(self, values, value_input_option="USER_ENTERED"):
        del value_input_option
        self.rows.append(dict(zip(self.headers, values)))

    def batch_update(self, updates, value_input_option="USER_ENTERED"):
        del value_input_option
        for update in updates:
            match = re.fullmatch(r"([A-Z]+)(\d+)", update["range"])
            assert match
            column = 0
            for character in match.group(1):
                column = column * 26 + ord(character) - 64
            row_index = int(match.group(2)) - 2
            self.rows[row_index][self.headers[column - 1]] = update["values"][0][0]


class Client:
    def __init__(self, sheets):
        self.sheets = sheets

    def _ensure_tab(self, logical, _headers):
        return self.sheets[logical]

    def _call_with_rate_limit_retry(self, _label, callback):
        return callback()


post_url = "https://www.threads.com/@approved/post/ABC123"
post_id = "sp_src_threads_ABC123"
media_id = f"spm_{post_id}_0"
post_headers = ["source_post_id", "canonical_post_url"]
media_headers = [
    "source_post_media_id",
    "source_post_id",
    "media_index",
    "original_media_url",
    "canonical_post_url",
    "acquisition_method",
    "resolver_backend",
    "thumbnail_url",
    "media_type",
    "download_status",
    "cloudinary_status",
    "last_error",
    "updated_at",
]
client = Client(
    {
        "source_posts": Worksheet(
            post_headers,
            [{"source_post_id": post_id, "canonical_post_url": post_url}],
        ),
        "source_post_media": Worksheet(
            media_headers,
            [
                {
                    "source_post_media_id": media_id,
                    "source_post_id": post_id,
                    "media_index": "0",
                    "original_media_url": "https://cdninstagram.com/expired.mp4",
                    "canonical_post_url": post_url,
                    "media_type": "video",
                    "download_status": "SKIPPED_EXTERNAL_UNAVAILABLE",
                    "cloudinary_status": "PENDING",
                    "last_error": "ingest_skipped:HTTPError",
                }
            ],
        ),
    }
)
post = NormalizedSourcePost(
    source_post_id=post_id,
    source_id="src_threads",
    target_account_id="night_scout",
    platform="threads",
    profile_url="https://www.threads.com/@approved",
    canonical_post_url=post_url,
    external_post_id="ABC123",
    original_post_text="same post",
    published_at="",
    author_name="approved",
    author_handle="approved",
    media_items=(
        NormalizedMediaItem(
            source_post_media_id=media_id,
            source_post_id=post_id,
            media_index=0,
            media_type="video",
            canonical_post_url=post_url,
            original_media_url="https://cdninstagram.com/fresh.mp4",
            resolver_backend="threads_public_http",
        ),
    ),
    engagement={},
    collection_backend="threads_public_http",
    backend_version="test",
    content_hash="hash",
    discovered_at="now",
)
result = acquisition.persist(client, [post])
row = client.sheets["source_post_media"].rows[0]
assert result["refreshed_source_post_media"] == 1
assert row["original_media_url"] == "https://cdninstagram.com/fresh.mp4"
assert row["download_status"] == "PENDING"
assert row["source_post_id"] == post_id
print("PASS test_acquisition_refreshes_volatile_threads_media.py")
