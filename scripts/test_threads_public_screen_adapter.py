#!/usr/bin/env python3
"""Focused contract for bounded rendered Threads profile discovery."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.threads_public import ThreadsPublicScreenAdapter  # noqa: E402

PROFILE = "https://www.threads.com/@target"


def href_loader(_: str, __: int) -> list[str]:
    return [
        "/@other/post/ignore-me",
        "/@target/post/first",
        "https://www.threads.com/@target/post/second?x=tracking",
        "/@target/post/first",
    ]


def html_loader(url: str) -> str:
    if url == PROFILE:
        return ""
    return '<meta property="og:description" content="公開投稿本文">'


adapter = ThreadsPublicScreenAdapter(html_loader=html_loader, href_loader=href_loader)
posts = adapter.acquire(
    {"source_id": "src", "source_url": PROFILE, "target_account_ids": ["night_scout"]},
    limit=2,
)

backfill = adapter.acquire(
    {
        "source_id": "src",
        "source_url": PROFILE,
        "target_account_ids": ["night_scout"],
        "_discovery_start_position": 2,
    },
    limit=1,
)

checks = {
    "only configured handle": [post.author_handle for post in posts] == ["target", "target"],
    "individual post urls": [post.external_post_id for post in posts] == ["first", "second"],
    "deduplicated": len(posts) == 2,
    "no profile parent": all("/post/" in post.canonical_post_url for post in posts),
    "bounded start position": [post.external_post_id for post in backfill] == ["second"],
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
