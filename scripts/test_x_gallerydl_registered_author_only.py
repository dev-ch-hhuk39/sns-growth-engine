#!/usr/bin/env python3
"""X profile metadata must never grant registered-source provenance to third-party posts."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import acquisition.x_gallerydl as xg  # noqa: E402


SOURCE = {
    "source_id": "src_test_x_owner",
    "source_platform": "x",
    "source_url": "https://x.com/approved_owner",
    "source_handle": "@approved_owner",
    "target_account_ids": ["night_scout"],
    "x_read_only": True,
}

rows = [
    {
        "post_url": "https://x.com/approved_owner/status/111",
        "tweet_id": "111",
        "tweet_content": "registered owner post",
        "url": "https://video.twimg.com/ext_tw_video/111/pu/vid/a.mp4?tag=1",
        "extension": "mp4",
    },
    {
        "post_url": "https://x.com/third_party/status/222",
        "tweet_id": "222",
        "tweet_content": "third party reposted content",
        "url": "https://video.twimg.com/ext_tw_video/222/pu/vid/b.mp4?tag=1",
        "extension": "mp4",
    },
]

captured: list[list[str]] = []
original_run = xg.subprocess.run
original_which = xg.shutil.which
try:
    xg.shutil.which = lambda _name: "/usr/local/bin/gallery-dl"

    def fake_run(command, **_kwargs):
        captured.append(list(command))
        return SimpleNamespace(
            returncode=0,
            stdout="\n".join(json.dumps(row) for row in rows),
            stderr="",
        )

    xg.subprocess.run = fake_run
    posts = xg.XGalleryDlProfileAdapter().acquire(SOURCE, limit=5)
finally:
    xg.subprocess.run = original_run
    xg.shutil.which = original_which

assert len(posts) == 1, [post.canonical_post_url for post in posts]
post = posts[0]
assert post.canonical_post_url == "https://x.com/approved_owner/status/111"
assert post.author_handle == "approved_owner"
assert len(post.media_items) == 1
assert post.media_items[0].media_type == "video"

command = captured[0]
assert "--config-ignore" in command
assert "--no-input" in command
assert "--no-download" in command
for option in (
    "extractor.twitter.retweets=false",
    "extractor.twitter.quoted=false",
    "extractor.twitter.replies=false",
    "extractor.twitter.conversations=false",
    "extractor.twitter.expand=false",
):
    assert option in command, option

print("PASS test_x_gallerydl_registered_author_only.py")
