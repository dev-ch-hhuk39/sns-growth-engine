#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT / "src"),
)

from acquisition.threads_public import (
    ThreadsPublicProfileAdapter,
)
from acquisition.tiktok_public import (
    TikTokPublicProfileAdapter,
)
from acquisition.ytdlp import (
    YtDlpProfilePostAdapter,
)


threads_profile = (
    '<a href="/@sample/post/p1">1</a>'
    '<a href="/@sample/post/p2">2</a>'
    '<a href="/@sample/post/p3">3</a>'
    '<a href="/@sample/post/p4">4</a>'
    '<a href="/@sample/post/p5">5</a>'
)


def threads_loader(url: str) -> str:
    if url.endswith("@sample"):
        return threads_profile

    return (
        '<meta property="og:description" '
        'content="post">'
        '<meta property="og:image" '
        f'content="https://cdn.example/'
        f'{url.rsplit("/", 1)[-1]}.jpg">'
    )


threads = ThreadsPublicProfileAdapter(html_loader=threads_loader)

threads_posts = threads.acquire(
    {
        "source_id": "src_threads",
        "source_url": ("https://www.threads.com/" "@sample"),
        "target_account_ids": ["night_scout"],
        "_discovery_start_position": 3,
    },
    limit=2,
)

assert [item.external_post_id for item in threads_posts] == [
    "p3",
    "p4",
]

assert all(item.media_count == 1 for item in threads_posts)


tiktok_profile = " ".join(
    ("https://www.tiktok.com/" f"@sample/video/{number}")
    for number in (
        101,
        102,
        103,
        104,
        105,
    )
)

tiktok = TikTokPublicProfileAdapter(html_loader=lambda url: (tiktok_profile))

tiktok_posts = tiktok.acquire(
    {
        "source_id": "src_tiktok",
        "source_platform": "tiktok",
        "source_url": ("https://www.tiktok.com/" "@sample"),
        "target_account_ids": ["liver_manager"],
        "_discovery_start_position": 3,
    },
    limit=2,
)

assert [item.external_post_id for item in tiktok_posts] == [
    "103",
    "104",
]


captured_options = {}


class FakeYoutubeDL:
    def __init__(
        self,
        options,
    ):
        captured_options.update(options)

    def extract_info(
        self,
        url,
        download=False,
    ):
        assert download is False

        return {
            "entries": [
                {
                    "id": "abcdefghijk",
                    "webpage_url": ("https://www.youtube.com/" "watch?v=abcdefghijk"),
                    "title": "one",
                },
                {
                    "id": "lmnopqrstuv",
                    "webpage_url": ("https://www.youtube.com/" "watch?v=lmnopqrstuv"),
                    "title": "two",
                },
                {
                    "id": "wxyzABCDEF1",
                    "webpage_url": ("https://www.youtube.com/" "watch?v=wxyzABCDEF1"),
                    "title": "three",
                },
            ]
        }


original_ytdlp = sys.modules.get("yt_dlp")

sys.modules["yt_dlp"] = SimpleNamespace(YoutubeDL=FakeYoutubeDL)

try:
    youtube = YtDlpProfilePostAdapter()

    youtube_posts = youtube.acquire(
        {
            "source_id": "src_youtube",
            "source_platform": "youtube",
            "source_url": ("https://www.youtube.com/" "channel/" "UC0000000000000000000000"),
            "target_account_ids": ["night_scout"],
            "_discovery_start_position": 7,
        },
        limit=3,
    )
finally:
    if original_ytdlp is None:
        sys.modules.pop(
            "yt_dlp",
            None,
        )
    else:
        sys.modules["yt_dlp"] = original_ytdlp


assert captured_options["playliststart"] == 7

assert captured_options["playlistend"] == 9

assert len(youtube_posts) == 3


print("PASS " "test_profile_adapters_respect_" "discovery_start_position.py")
