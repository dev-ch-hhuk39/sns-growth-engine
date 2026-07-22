#!/usr/bin/env python3
"""The latest permission ledger row is the only runtime authority."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]
import ingest_direct_reference_media as ingest


class Worksheet:
    def get_all_records(self):
        return [
            {"source_id": "source_1", "permission_status": "pending", "rights_status": "unknown", "revoked": "false", "updated_at": "2026-07-01T00:00:00+00:00"},
            {"source_id": "source_1", "permission_status": "approved", "rights_status": "approved_creator_clip", "revoked": "false", "updated_at": "2026-07-22T00:00:00+00:00", "allow_download": "true", "allow_cloudinary_storage": "true", "allow_original_repost": "true", "allow_new_caption": "true"},
        ]


class Client:
    def _ensure_tab(self, *_args):
        return None

    def _ws(self, _logical):
        return Worksheet()

    def _call_with_rate_limit_retry(self, _label, operation):
        return operation()


assert ingest.permission_ok(Client(), "source_1") is True
print("PASS test_direct_media_permission_latest_row.py")
