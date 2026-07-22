#!/usr/bin/env python3
"""External provider challenges must not invite an auth bypass or fail all preparation."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import ingest_direct_reference_media as ingest


class Client:
    def _ensure_tab(self, *_args):
        return None


original_record = ingest.record
original_download = ingest.download_with_ytdlp
original_update = ingest.update_media_row
original_safe_url = ingest.safe_https_url
try:
    ingest.record = lambda *_args, **_kwargs: None
    ingest.update_media_row = lambda *_args, **_kwargs: None
    ingest.safe_https_url = lambda *_args, **_kwargs: True

    def bot_challenge(*_args, **_kwargs):
        raise RuntimeError("Sign in to confirm you're not a bot")

    ingest.download_with_ytdlp = bot_challenge
    result = ingest.ingest_one(
        Client(),
        {"platform": "youtube", "source_post_id": "post_1"},
        {
            "source_post_media_id": "media_1",
            "canonical_post_url": "https://youtube.com/watch?v=abc123",
            "original_media_url": "https://youtube.com/watch?v=abc123",
            "media_type": "video",
        },
    )
finally:
    ingest.record = original_record
    ingest.download_with_ytdlp = original_download
    ingest.update_media_row = original_update
    ingest.safe_https_url = original_safe_url

assert result["status"] == "SKIPPED_EXTERNAL_UNAVAILABLE", result
assert result["reason"] == "ingest_skipped:RuntimeError", result
print("PASS test_direct_media_external_unavailable_is_safe_skip.py")
