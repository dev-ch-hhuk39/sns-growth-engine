#!/usr/bin/env python3
"""Rendered Threads session backend keeps text and ordered media post-bound."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.factory import build_router  # noqa: E402
from acquisition.threads_public import ThreadsBrowserSessionAdapter  # noqa: E402


SOURCE = {
    "source_id": "src_ns_threads_test",
    "source_url": "https://www.threads.com/@target",
    "target_account_ids": ["night_scout"],
}


def rendered(_source: dict, _limit: int) -> list[dict]:
    return [
        {
            "post_url": "https://www.threads.com/@target/post/abc123?tracking=1",
            "text_candidates": [
                "target",
                "ログイン",
                "店選びは時給だけでなく、客層と出勤ペースまで確認した方が続けやすい。",
            ],
            "published_at": "2026-08-10T01:00:00Z",
            "media": [
                {
                    "media_type": "image",
                    "url": "https://cdn.example/profile_pic.jpg",
                    "width": "120",
                    "height": "120",
                },
                {
                    "media_type": "video",
                    "url": "https://video.cdninstagram.com/post.mp4?x=1",
                    "poster": "https://cdninstagram.com/poster.jpg",
                    "width": "1920",
                    "height": "1080",
                    "duration_seconds": "18.5",
                },
                {
                    "media_type": "image",
                    "url": "https://scontent.cdninstagram.com/second.jpg",
                    "width": "1080",
                    "height": "1350",
                },
            ],
        },
        {
            "post_url": "https://www.threads.com/@other/post/wrong",
            "text_candidates": ["別アカウント"],
            "media": [],
        },
    ]


adapter = ThreadsBrowserSessionAdapter(render_loader=rendered)
posts = adapter.acquire(SOURCE, limit=5)
post = posts[0]
routing = json.loads(
    (ROOT / "config" / "source_backend_routing.json").read_text(encoding="utf-8")
)
router = build_router()

checks = {
    "configured account only": len(posts) == 1 and post.author_handle == "target",
    "individual parent retained": post.canonical_post_url.endswith("/@target/post/abc123"),
    "login boilerplate removed": "ログイン" not in post.original_post_text,
    "source text retained": "店選び" in post.original_post_text,
    "ordered post media": [item.media_type for item in post.media_items] == ["video", "image"],
    "all children share parent": all(item.source_post_id == post.source_post_id for item in post.media_items),
    "dimensions retained": (post.media_items[0].width, post.media_items[0].height) == ("1920", "1080"),
    "session is configured primary": routing["routes"]["threads.profile_posts"]["primary"] == "threads_browser_session",
    "independent public fallbacks remain": routing["routes"]["threads.profile_posts"]["fallbacks"] == [
        "threads_public_screen", "threads_public_playwright", "threads_public_http"
    ],
    "factory registers session backend": "threads_browser_session" in router.adapters,
}

for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
