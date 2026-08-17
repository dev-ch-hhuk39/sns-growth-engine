from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.factory import build_router  # noqa: E402
from acquisition.failures import FailureCategory, classify_failure  # noqa: E402
from acquisition.threads_cli import (  # noqa: E402
    ThreadsCliPublicAdapter,
    ThreadsLoggedOutGraphQLAdapter,
)

SOURCE = {
    "source_id": "src_ns_threads_test",
    "source_url": "https://www.threads.com/@target",
    "target_account_ids": ["night_scout"],
}


def test_threads_cli_primary_is_anonymous_bounded_and_parent_safe(monkeypatch) -> None:
    monkeypatch.setenv("THREADS_TOKEN", "must-not-leak")
    monkeypatch.setenv("THREADS_SESSION", "must-not-leak")
    observed: dict = {}

    def runner(command, environment, timeout):
        observed.update(command=command, environment=environment, timeout=timeout)
        payload = [{
            "id": "123",
            "shortcode": "ABC",
            "text": "店選びは時給だけでなく、客層と出勤ペースまで確認する。",
            "media_type": "CAROUSEL_ALBUM",
            "media_urls": [
                "https://cdn.example/first.jpg?x=1",
                "https://cdn.example/second.mp4?x=2",
            ],
            "permalink": "https://www.threads.com/@target/post/ABC?tracking=1",
            "username": "target",
            "timestamp": "2026-08-17T00:00:00Z",
        }]
        return 0, json.dumps(payload), ""

    posts = ThreadsCliPublicAdapter(runner=runner, binary_path="/tmp/th").acquire(
        SOURCE, limit=99
    )
    assert observed["command"][-4:] == ["-n", "5", "-o", "json"]
    assert "THREADS_TOKEN" not in observed["environment"]
    assert "THREADS_SESSION" not in observed["environment"]
    assert observed["timeout"] == 90
    assert len(posts) == 1
    assert posts[0].canonical_post_url == "https://www.threads.com/@target/post/ABC"
    assert [item.media_index for item in posts[0].media_items] == [0, 1]
    assert [item.media_type for item in posts[0].media_items] == ["image", "video"]
    assert all(item.source_post_id == posts[0].source_post_id for item in posts[0].media_items)


def test_logged_out_graphql_fallback_normalizes_public_post() -> None:
    observed: dict = {}

    def poster(url, headers, body):
        observed.update(url=url, headers=headers, body=parse_qs(body.decode()))
        return {"data": {"edges": [{"node": {"thread_items": [{"post": {
            "pk": "456",
            "code": "DEF",
            "caption": {"text": "初見が入りやすい配信は、最初の一言が具体的。"},
            "taken_at": 1786924800,
            "media_type": 2,
            "video_versions": [{"url": "https://cdn.example/post.mp4"}],
            "user": {"pk": "99", "username": "target"},
            "like_count": 7,
            "text_post_app_info": {
                "direct_reply_count": 2,
                "repost_count": 1,
                "quote_count": 0,
                "is_quote_post": False,
                "reply_to_author": None,
            },
        }}]}}]}}

    adapter = ThreadsLoggedOutGraphQLAdapter(
        profile_loader=lambda _source: {"id": "99", "username": "target"},
        json_poster=poster,
    )
    posts = adapter.acquire(SOURCE, limit=2)
    assert observed["url"].endswith("/api/graphql")
    assert observed["body"]["doc_id"] == ["33773912952222602"]
    variables = json.loads(observed["body"]["variables"][0])
    assert variables["__relay_internal__pv__BarcelonaIsCrawlerrelayprovider"] is True
    assert posts[0].external_post_id == "456"
    assert posts[0].media_items[0].media_type == "video"
    assert posts[0].author_handle == "target"


def test_threads_route_order_and_circuit_policy() -> None:
    route = build_router().routes["threads.profile_posts"]
    assert route.primary == "threads_cli_public"
    assert route.fallbacks == (
        "threads_logged_out_graphql",
        "threads_public_screen",
    )
    assert route.circuit_failure_threshold == 3
    assert route.cooldown_seconds == 900


def test_all_threads_backends_failed_is_deferred() -> None:
    reason = (
        "all_backends_failed:threads_cli_public:no_public_posts,"
        "threads_logged_out_graphql:profile_not_found,"
        "threads_public_screen:public_screen_failed"
    )
    assert classify_failure("threads", reason) is FailureCategory.DEFERRED
