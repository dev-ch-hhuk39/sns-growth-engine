#!/usr/bin/env python3
"""Legacy Threads browser adapter may remain, but must not be active routing."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.factory import build_router  # noqa: E402
from acquisition.threads_public import ThreadsBrowserSessionAdapter  # noqa: E402

SOURCE = {
    "source_id": "src_ns_threads_test",
    "source_url": "https://www.threads.com/@target",
    "target_account_ids": ["night_scout"],
}


def rendered(_source: dict, _limit: int) -> list[dict]:
    return [{
        "post_url": "https://www.threads.com/@target/post/abc123?tracking=1",
        "text_candidates": ["target", "ログイン", "店選びは時給だけでなく、客層と出勤ペースまで確認した方が続けやすい。"],
        "published_at": "2026-08-10T01:00:00Z",
        "media": [
            {"media_type": "image", "url": "https://cdn.example/profile_pic.jpg", "width": "120", "height": "120"},
            {"media_type": "video", "url": "https://video.cdninstagram.com/post.mp4?x=1", "poster": "https://cdninstagram.com/poster.jpg", "width": "1920", "height": "1080", "duration_seconds": "18.5"},
            {"media_type": "image", "url": "https://scontent.cdninstagram.com/second.jpg", "width": "1080", "height": "1350"},
        ],
    }]

adapter = ThreadsBrowserSessionAdapter(render_loader=rendered)
posts = adapter.acquire(SOURCE, limit=5)
post = posts[0]
routing = json.loads((ROOT / "config/source_backend_routing.json").read_text(encoding="utf-8"))
router = build_router()
active_names = [
    backend
    for route in routing["routes"].values()
    for backend in [route["primary"], *route.get("fallbacks", [])]
]
checks = {
    "legacy adapter still parses parent": len(posts) == 1 and post.author_handle == "target",
    "legacy adapter retains ordered media": [item.media_type for item in post.media_items] == ["video", "image"],
    "threads has no active acquisition route": not any(key.startswith("threads.") for key in routing["routes"]),
    "threads browser session is inactive": "threads_browser_session" not in active_names,
    "threads playwright is inactive": all("playwright" not in name for name in active_names),
    "factory may retain legacy session adapter": "threads_browser_session" in router.adapters,
}
for name, passed in checks.items():
    print(f"{'PASS' if passed else 'FAIL'} {name}")
raise SystemExit(0 if all(checks.values()) else 1)
