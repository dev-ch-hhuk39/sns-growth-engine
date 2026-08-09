#!/usr/bin/env python3
"""Threads profile collection must use the shared multi-backend router."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import collect_source_posts as collector


post = SimpleNamespace(
    canonical_post_url="https://www.threads.com/@target/post/abc123",
    external_post_id="abc123",
    original_post_text="公開投稿本文",
    published_at="2026-08-09T00:00:00Z",
    author_handle="target",
    media_items=(SimpleNamespace(original_media_url="https://cdn.example/one.jpg"),),
)


class FakeRouter:
    def route(self, capability, source, *, limit):
        assert capability == "threads.profile_posts"
        assert source["source_url"] == "https://www.threads.com/@target"
        assert limit == 2
        return SimpleNamespace(posts=[post], backend_name="threads_public_screen", fallback_used=True)


import acquisition.factory

original = acquisition.factory.build_router
acquisition.factory.build_router = lambda: FakeRouter()
try:
    result = collector.fetch_threads_account_posts(
        {"source_id": "src", "source_url": "https://www.threads.com/@target"}, limit=2
    )
finally:
    acquisition.factory.build_router = original

checks = {
    "router success": result["status"] == "FETCHED",
    "screen fallback recorded": result["backend"] == "threads_public_screen" and result["fallback_used"],
    "individual parent only": result["rows"][0]["post_url"].endswith("/post/abc123"),
    "ordered media retained": result["rows"][0]["media_urls"] == ["https://cdn.example/one.jpg"],
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
