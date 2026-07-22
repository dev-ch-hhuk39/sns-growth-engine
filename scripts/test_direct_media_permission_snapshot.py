#!/usr/bin/env python3
"""Selection must read the permission ledger once per preparation attempt."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import ingest_direct_reference_media as ingest


class Worksheet:
    def __init__(self, rows):
        self.rows = rows

    def get_all_records(self):
        return self.rows


class Client:
    def __init__(self):
        self.permission_reads = 0
        self.rows = {
            "source_posts": [{"source_post_id": "post", "source_id": "approved", "target_account_id": "night_scout", "platform": "youtube"}],
            "source_post_media": [
                {"source_post_media_id": "one", "source_post_id": "post", "original_media_url": "https://www.youtube.com/watch?v=one", "created_at": "2026-07-01T00:00:00+00:00"},
                {"source_post_media_id": "two", "source_post_id": "post", "original_media_url": "https://www.youtube.com/watch?v=two", "created_at": "2026-07-02T00:00:00+00:00"},
            ],
            "media_permissions": [{"source_id": "approved", "permission_status": "approved", "rights_status": "approved_creator_clip", "updated_at": "2026-07-02T00:00:00+00:00", "allow_download": "true", "allow_cloudinary_storage": "true", "allow_original_repost": "true", "allow_new_caption": "true", "revoked": "false"}],
        }

    def _ensure_tab(self, *_args):
        return None

    def _call_with_rate_limit_retry(self, _name, callback):
        return callback()

    def _ws(self, name):
        if name == "media_permissions":
            self.permission_reads += 1
        return Worksheet(self.rows[name])


client = Client()
permissions = ingest.permission_rows(client)
selected = ingest.select_pending_media_id(client, "night_scout", permissions=permissions)
checks = [
    ("selects a permitted candidate", selected == "one"),
    ("uses one permission snapshot", client.permission_reads == 1),
]
for name, passed in checks:
    print(f"  {'PASS' if passed else 'FAIL'} {name}")
failed = [name for name, passed in checks if not passed]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
