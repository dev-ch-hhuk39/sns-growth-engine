#!/usr/bin/env python3
"""A profile/avatar OG image must never be mistaken for post-bound media."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.threads_public import parse_public_post_html

post = parse_public_post_html(
    {"source_id": "src", "source_url": "https://www.threads.com/@target", "target_account_id": "night_scout"},
    "https://www.threads.com/@target/post/abc",
    '<meta property="og:description" content="本文"><meta property="og:image" content="https://cdn.example/avatar.jpg">',
)
checks = {
    "text retained": post.original_post_text == "本文",
    "og image is thumbnail only": post.media_count == 0,
    "no unsafe media child": not post.media_items,
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
