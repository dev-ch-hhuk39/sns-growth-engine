#!/usr/bin/env python3
"""Direct preparation uses bounded, parent-safe video backfill."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import acquire_approved_source_posts as acquisition  # noqa: E402
from acquisition.models import NormalizedMediaItem, NormalizedSourcePost  # noqa: E402
from acquisition.threads_public import bounded_profile_scroll_attempts  # noqa: E402


def post(media_types: list[str]) -> NormalizedSourcePost:
    post_id = "sp_source_one"
    return NormalizedSourcePost(
        source_post_id=post_id,
        source_id="source",
        target_account_id="night_scout",
        platform="threads",
        profile_url="https://www.threads.com/@source",
        canonical_post_url="https://www.threads.com/@source/post/one",
        external_post_id="one",
        original_post_text="投稿本文",
        published_at="2026-08-10T00:00:00Z",
        author_name="",
        author_handle="source",
        media_items=tuple(
            NormalizedMediaItem(
                source_post_media_id=f"spm_{index}",
                source_post_id=post_id,
                media_index=index,
                media_type=media_type,
                canonical_post_url="https://www.threads.com/@source/post/one",
                original_media_url=f"https://cdn.example/{index}",
                resolver_backend="fixture",
            )
            for index, media_type in enumerate(media_types)
        ),
        engagement={},
        collection_backend="fixture",
        backend_version="1",
        content_hash="hash",
        discovered_at="2026-08-10T00:00:00Z",
    )


workflow = (
    ROOT / ".github" / "workflows" / "direct-media-preparation.yml"
).read_text(encoding="utf-8")

progress = acquisition.selection_with_scan_progress(
    {"max_scanned_position": 0},
    {"start_position": 31},
    30,
)

checks = {
    "video parent accepted": acquisition.post_matches_media_filter(
        post(["video", "video"]), "video-only"
    ),
    "mixed parent rejected": not acquisition.post_matches_media_filter(
        post(["video", "image"]), "video-only"
    ),
    "image parent rejected": not acquisition.post_matches_media_filter(
        post(["image"]), "video-only"
    ),
    "empty parent rejected": not acquisition.post_matches_media_filter(
        post([]), "video-only"
    ),
    "default keeps parent": acquisition.post_matches_media_filter(
        post(["image"]), "any"
    ),
    "scroll remains bounded": bounded_profile_scroll_attempts(1000) == 12,
    "small scan remains bounded": bounded_profile_scroll_attempts(12) == 3,
    "workflow requests video only": "--media-filter video-only" in workflow,
    "workflow requests backfill": "--force-backfill" in workflow,
    "workflow scan cap is thirty": "--max-posts 30" in workflow,
    "empty video window advances cursor": progress["max_scanned_position"] == 60,
}

for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")

raise SystemExit(0 if all(checks.values()) else 1)
