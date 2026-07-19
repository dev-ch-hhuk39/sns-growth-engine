#!/usr/bin/env python3
"""TikTok profile acquisition has a bounded, real fallback route."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.router import AdapterRouter, BackendFailure, BackendRoute
from acquisition.tiktok_public import MAX_PUBLIC_PROFILE_POSTS, TikTokPublicProfileAdapter, extract_profile_video_urls


class FailingPrimary:
    backend_name = "yt_dlp"
    backend_version = "test"

    def acquire(self, _source, *, limit):
        raise BackendFailure("primary_unavailable")


source = {
    "source_id": "src_lm_tt_test",
    "source_platform": "tiktok",
    "source_url": "https://www.tiktok.com/@approved.creator",
    "target_account_ids": ["liver_manager"],
}
html = "".join(
    f'<a href="/@approved.creator/video/{7000000000000000000 + index}">video</a>'
    for index in range(30)
) + '<a href="/@other.creator/video/7999999999999999999">other</a>'
fallback = TikTokPublicProfileAdapter(html_loader=lambda _url: html)
router = AdapterRouter(
    {"yt_dlp": FailingPrimary(), "tiktok_public_playwright": fallback},
    {"tiktok.profile_posts": BackendRoute("tiktok.profile_posts", "yt_dlp", ("tiktok_public_playwright",), 1)},
)
result = router.route("tiktok.profile_posts", source, limit=50)
routing = json.loads((ROOT / "config/source_backend_routing.json").read_text(encoding="utf-8"))
urls = extract_profile_video_urls(html, source["source_url"], limit=50)

checks = {
    "configured fallback": routing["routes"]["tiktok.profile_posts"]["fallbacks"] == ["tiktok_public_playwright"],
    "fallback selected": result.backend_name == "tiktok_public_playwright" and result.fallback_used,
    "bounded limit": len(result.posts) == MAX_PUBLIC_PROFILE_POSTS == len(urls),
    "same profile only": all("@approved.creator/video/" in post.canonical_post_url for post in result.posts),
    "normalized parent media": all(post.media_items[0].source_post_id == post.source_post_id for post in result.posts),
}
for label, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'} {label}")
raise SystemExit(0 if all(checks.values()) else 1)
