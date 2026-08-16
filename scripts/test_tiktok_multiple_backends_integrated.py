#!/usr/bin/env python3
"""TikTok reference discovery keeps yt-dlp primary + bounded gallery-dl fallback, no browser."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.router import AdapterRouter, BackendFailure, BackendRoute  # noqa: E402
import acquisition.tiktok_gallerydl as gallerymod  # noqa: E402
from acquisition.tiktok_gallerydl import MAX_TIKTOK_PROFILE_POSTS, TikTokGalleryDlProfileAdapter  # noqa: E402


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
    "fetch_enabled": True,
}
rows = []
for index in range(30):
    video_id = 7000000000000000000 + index
    rows.append(json.dumps({
        "webpage_url": f"https://www.tiktok.com/@approved.creator/video/{video_id}",
        "url": f"https://v16.tiktokcdn.com/{video_id}.mp4",
        "description": f"post {index}",
    }))
stdout = "\n".join(rows)

original_which = gallerymod.shutil.which
original_run = gallerymod.subprocess.run
try:
    gallerymod.shutil.which = lambda _name: "/usr/local/bin/gallery-dl"
    gallerymod.subprocess.run = lambda *_a, **_k: SimpleNamespace(returncode=0, stdout=stdout, stderr="")
    fallback = TikTokGalleryDlProfileAdapter()
    router = AdapterRouter(
        {"yt_dlp": FailingPrimary(), "tiktok_gallery_dl": fallback},
        {"tiktok.profile_posts": BackendRoute("tiktok.profile_posts", "yt_dlp", ("tiktok_gallery_dl",), 1)},
    )
    result = router.route("tiktok.profile_posts", source, limit=50)
finally:
    gallerymod.shutil.which = original_which
    gallerymod.subprocess.run = original_run

routing = json.loads((ROOT / "config/source_backend_routing.json").read_text(encoding="utf-8"))
route = routing["routes"]["tiktok.profile_posts"]
checks = {
    "configured non-browser fallback": route["fallbacks"] == ["tiktok_gallery_dl"],
    "playwright removed from active fallback": all("playwright" not in name for name in route.get("fallbacks", [])),
    "gallery fallback selected": result.backend_name == "tiktok_gallery_dl" and result.fallback_used,
    "bounded limit": len(result.posts) == MAX_TIKTOK_PROFILE_POSTS,
    "same profile only": all("@approved.creator/video/" in post.canonical_post_url for post in result.posts),
    "normalized parent media": all(post.media_items and post.media_items[0].source_post_id == post.source_post_id for post in result.posts),
}
for label, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'} {label}")
raise SystemExit(0 if all(checks.values()) else 1)
