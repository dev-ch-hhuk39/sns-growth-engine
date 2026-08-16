import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.factory import build_router  # noqa: E402
from acquisition.router import BackendFailure  # noqa: E402
from acquisition.tiktok_embed import TikTokPublicEmbedAdapter, parse_public_embed  # noqa: E402


def _page(handle="allowed", *, private=False):
    videos = [
        {
            "id": "7649682547588254994",
            "authorUniqueId": handle,
            "desc": "配信前に決めること",
            "playAddr": "https://v16.example.test/video-one.mp4",
            "originCoverUrl": "https://p16.example.test/cover-one.jpeg",
            "playCount": 1200,
            "width": 720,
            "height": 1280,
            "privateItem": private,
        },
        {
            "id": "7644120038315805959",
            "authorUniqueId": handle,
            "desc": "初見が入りやすい配信",
            "playAddr": "https://v16.example.test/video-two.mp4",
            "coverUrl": "https://p16.example.test/cover-two.jpeg",
            "playCount": 900,
            "width": 1080,
            "height": 1920,
            "privateItem": private,
        },
    ]
    payload = {
        "source": {
            "data": {
                f"/embed/@{handle}": {
                    "userInfo": {"uniqueId": handle},
                    "videoList": videos,
                }
            }
        }
    }
    return '<html><script id="__FRONTITY_CONNECT_STATE__">' + json.dumps(payload) + "</script></html>"


def _source(handle="allowed"):
    return {
        "source_id": "src_lm_tt",
        "source_platform": "tiktok",
        "source_url": f"https://www.tiktok.com/@{handle}",
        "target_account_ids": ["liver_manager"],
        "fetch_enabled": True,
    }


def test_public_embed_discovers_bounded_individual_posts_with_parent_integrity():
    adapter = TikTokPublicEmbedAdapter(lambda _url: _page())
    posts = adapter.acquire(_source(), limit=1)
    assert len(posts) == 1
    post = posts[0]
    assert post.canonical_post_url == "https://www.tiktok.com/@allowed/video/7649682547588254994"
    assert post.author_handle == "allowed"
    assert post.original_post_text == "配信前に決めること"
    assert post.media_items[0].source_post_id == post.source_post_id
    assert post.media_items[0].canonical_post_url == post.canonical_post_url
    assert post.media_items[0].original_media_url.endswith("video-one.mp4")
    assert post.media_items[0].media_index == 0


def test_public_embed_rejects_mismatched_author_without_guessing():
    with pytest.raises(BackendFailure, match="author_mismatch"):
        parse_public_embed(_page("different"), expected_handle="allowed", limit=3)


def test_public_embed_fails_closed_when_payload_or_public_videos_are_missing():
    with pytest.raises(BackendFailure, match="payload_unavailable"):
        parse_public_embed("<html></html>", expected_handle="allowed", limit=3)
    with pytest.raises(BackendFailure, match="individual_posts_unavailable"):
        parse_public_embed(_page(private=True), expected_handle="allowed", limit=3)


def test_public_embed_is_primary_and_gallery_dl_is_only_fallback():
    route = build_router().routes["tiktok.profile_posts"]
    assert route.primary == "tiktok_public_embed"
    assert route.fallbacks == ("tiktok_gallery_dl",)
