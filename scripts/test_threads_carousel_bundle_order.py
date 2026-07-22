#!/usr/bin/env python3
"""Threads hydration carousel order is preserved under one source_post_id."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.threads_public import parse_public_post_html

source = {
    "source_id": "src_ns_threads_test",
    "source_url": "https://www.threads.com/@creator",
    "target_account_ids": ["night_scout"],
}
payload = {
    "post": {
        "carousel_media": [
            {"image_versions2": {"candidates": [{"url": "https://cdn.example/first.jpg"}]}},
            {"video_versions": [{"url": "https://cdn.example/second.mp4"}], "image_versions2": {"candidates": [{"url": "https://cdn.example/second-cover.jpg"}]}},
            {"image_versions2": {"candidates": [{"url": "https://cdn.example/third.jpg"}]}},
        ]
    }
}
page = (
    '<meta property="og:description" content="source-specific caption">'
    '<meta property="og:image" content="https://cdn.example/profile-avatar.jpg">'
    f'<script type="application/json">{json.dumps(payload)}</script>'
)
post = parse_public_post_html(source, "https://www.threads.com/@creator/post/ABC123", page)
items = list(post.media_items)
checks = {
    "all carousel items": len(items) == 3,
    "source order": [item.media_type for item in items] == ["image", "video", "image"],
    "exact URLs": [item.original_media_url for item in items] == [
        "https://cdn.example/first.jpg", "https://cdn.example/second.mp4", "https://cdn.example/third.jpg"
    ],
    "single parent": all(item.source_post_id == post.source_post_id for item in items),
    "stable media indices": [item.media_index for item in items] == [0, 1, 2],
    "avatar excluded": all("profile-avatar" not in item.original_media_url for item in items),
}
for label, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'} {label}")
raise SystemExit(0 if all(checks.values()) else 1)
