#!/usr/bin/env python3
"""Direct-media selection must skip unpermitted source-post media."""
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
        self.rows = {
            "source_posts": [
                {"source_post_id": "unpermitted", "source_id": "reference_only", "target_account_id": "night_scout", "platform": "threads"},
                {"source_post_id": "permitted", "source_id": "approved", "target_account_id": "night_scout", "platform": "youtube"},
            ],
            "source_post_media": [
                {"source_post_media_id": "old_unpermitted", "source_post_id": "unpermitted", "original_media_url": "https://www.threads.com/@ref/post/one", "created_at": "2026-07-01T00:00:00+00:00"},
                {"source_post_media_id": "new_permitted", "source_post_id": "permitted", "original_media_url": "https://www.youtube.com/watch?v=abc", "created_at": "2026-07-02T00:00:00+00:00"},
            ],
            "media_permissions": [
                {"source_id": "reference_only", "permission_status": "", "rights_status": "reference_only", "updated_at": "2026-07-01T00:00:00+00:00"},
                {"source_id": "approved", "permission_status": "approved", "rights_status": "approved_creator_clip", "updated_at": "2026-07-02T00:00:00+00:00", "allow_download": "true", "allow_cloudinary_storage": "true", "allow_original_repost": "true", "allow_new_caption": "true", "revoked": "false"},
            ],
        }

    def _ensure_tab(self, *_args):
        return None

    def _call_with_rate_limit_retry(self, _name, callback):
        return callback()

    def _ws(self, name):
        return Worksheet(self.rows[name])


selected = ingest.select_pending_media_id(Client(), "night_scout")
checks = [("skips unpermitted media before selection", selected == "new_permitted")]
for name, passed in checks:
    print(f"  {'PASS' if passed else 'FAIL'} {name}")
failed = [name for name, passed in checks if not passed]
print(f"PASS: {len(checks) - len(failed)} / FAIL: {len(failed)}")
raise SystemExit(1 if failed else 0)
