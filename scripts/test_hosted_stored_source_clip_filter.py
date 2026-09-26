#!/usr/bin/env python3
"""Hosted clip filtering never falls back to an unverified platform source."""
from unittest.mock import patch

import run_media_production_pipeline as pipeline

videos = [
    {"source_video_id": "allowed", "source_id": "src-a", "account_id": "liver_manager"},
    {"source_video_id": "no-storage", "source_id": "src-b", "account_id": "liver_manager"},
    {"source_video_id": "cross-account", "source_id": "src-c", "account_id": "night_scout"},
]
context = {
    "source_post_row": {"source_post_id": "post-a"},
    "source_media_row": {"source_post_media_id": "media-a"},
    "media_assets_rows": [{"media_id": "asset-a"}],
    "media_permissions_rows": [{"permission_id": "permission-a"}],
    "registered_source_row": {"source_id": "src-a"},
}

def lookup(_client, row):
    return context if row["source_video_id"] in {"allowed", "no-storage"} else {}

def decision(video, *_args):
    return {"allowed": video["source_video_id"] == "allowed"}

with patch.object(pipeline, "_stored_full_source_context", side_effect=lookup), \
     patch.object(pipeline, "select_stored_full_source", side_effect=decision) as select:
    selected, rejected = pipeline.verified_stored_source_videos(
        object(), videos, account_id="liver_manager",
    )

assert [row["source_video_id"] for row in selected] == ["allowed"]
assert rejected == 2
assert select.call_count == 2
print("PASS test_hosted_stored_source_clip_filter.py")
