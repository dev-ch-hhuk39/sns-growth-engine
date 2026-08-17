#!/usr/bin/env python3
"""Threads reference collection uses the shared three-stage router."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import collect_source_posts as collector  # noqa: E402
from acquisition.models import NormalizedSourcePost  # noqa: E402
from acquisition.router import RouteResult  # noqa: E402


class _Router:
    def route(self, capability, source, *, limit):
        assert capability == "threads.profile_posts"
        assert limit == 2
        return RouteResult(
            backend_name="threads_cli_public",
            posts=[NormalizedSourcePost(
                source_post_id="sp_src_abc",
                source_id="src",
                target_account_id="night_scout",
                platform="threads",
                profile_url=source["source_url"],
                canonical_post_url="https://www.threads.com/@target/post/abc",
                external_post_id="abc",
                original_post_text="公開投稿の本文",
                published_at="2026-08-17T00:00:00Z",
            )],
        )


import acquisition.factory as factory  # noqa: E402
factory.build_router = lambda: _Router()


result = collector.fetch_threads_account_posts(
    {"source_id": "src", "source_url": "https://www.threads.com/@target"},
    limit=2,
)

checks = {
    "fetched": result["status"] == "FETCHED",
    "exact individual post": result["rows"][0]["post_url"].endswith("/post/abc"),
    "active primary backend": result["backend"] == "threads_cli_public",
    "no fallback": result["fallback_used"] is False,
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
