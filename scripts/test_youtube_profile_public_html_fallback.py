#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.ytdlp import YtDlpProfilePostAdapter  # noqa: E402


def html(entries: list[tuple[str, str]]) -> str:
    items = ",".join(
        '{"videoRenderer":{"videoId":"%s","title":{"simpleText":"%s"},'
        '"lengthText":{"simpleText":"0:20"}}}' % item
        for item in entries
    )
    return f'<script>var ytInitialData = {{"items":[{items}]}};</script>'


def lockup_html(entries: list[tuple[str, str]]) -> str:
    items = ",".join(
        '{"lockupViewModel":{"contentId":"%s","metadata":'
        '{"lockupMetadataViewModel":{"title":{"content":"%s"}}}}}' % item
        for item in entries
    )
    return f'<script>var ytInitialData = {{"items":[{items}]}};</script>'


class FakeResponse:
    def __init__(self, body: str):
        self.body = body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit: int):
        return self.body


class EmptyYoutubeDL:
    def __init__(self, _options):
        pass

    def extract_info(self, _url, download=False):
        assert download is False
        return {"entries": []}


def fake_urlopen(request, timeout=0):
    assert timeout == 20
    url = request.full_url
    if url.endswith("/videos"):
        return FakeResponse(
            lockup_html(
                [
                    ("videoAAAAA1", "通常動画A"),
                    ("videoAAAAA2", "通常動画B"),
                    ("videoAAAAA3", "通常動画C"),
                ]
            )
        )
    if url.endswith("/shorts"):
        return FakeResponse(
            html(
                [
                    ("shortBBBBB1", "Short A"),
                    ("shortBBBBB2", "Short B"),
                    ("shortBBBBB3", "Short C"),
                ]
            )
        )
    raise AssertionError(url)


original_ytdlp = sys.modules.get("yt_dlp")
sys.modules["yt_dlp"] = SimpleNamespace(YoutubeDL=EmptyYoutubeDL)
try:
    with patch("acquisition.ytdlp.urlopen", side_effect=fake_urlopen):
        posts = YtDlpProfilePostAdapter().acquire(
            {
                "source_id": "src_ns_youtube",
                "source_platform": "youtube",
                "source_handle": "@night_channel",
                "source_url": "https://www.youtube.com/@night_channel",
                "target_account_ids": ["night_scout"],
                "_discovery_start_position": 2,
            },
            limit=3,
        )
finally:
    if original_ytdlp is None:
        sys.modules.pop("yt_dlp", None)
    else:
        sys.modules["yt_dlp"] = original_ytdlp


assert [post.external_post_id for post in posts] == [
    "shortBBBBB1",
    "videoAAAAA2",
    "shortBBBBB2",
]
assert all(post.target_account_id == "night_scout" for post in posts)
assert all(post.collection_backend == "youtube_public_html" for post in posts)
assert all(post.media_count == 1 for post in posts)
assert all(post.media_items[0].canonical_post_url == post.canonical_post_url for post in posts)
assert all(post.original_post_text for post in posts)

print("PASS test_youtube_profile_public_html_fallback.py")
