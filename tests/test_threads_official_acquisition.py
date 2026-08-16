from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.threads_official import (  # noqa: E402
    ThreadsGraphPublicDiscoveryAdapter,
    ThreadsOEmbedDetailAdapter,
    normalize_graph_post,
)
from acquisition.threads_search import (  # noqa: E402
    ThreadsSearchIndexAdapter,
    extract_search_candidates,
)


SOURCE = {
    "source_id": "src_threads_test",
    "source_url": "https://www.threads.com/@me01_lsm",
    "target_account_ids": ["liver_manager"],
}


def graph_row(**overrides):
    row = {
        "id": "123456",
        "username": "me01_lsm",
        "permalink": "https://www.threads.com/@me01_lsm/post/ABC123",
        "text": "配信の入り口を整えると、初見さんは参加しやすくなる。",
        "timestamp": "2026-08-11T00:00:00+0000",
        "media_type": "VIDEO",
        "media_url": "https://cdn.example/video.mp4",
        "thumbnail_url": "https://cdn.example/thumb.jpg",
    }
    row.update(overrides)
    return row


def test_graph_missing_auth_fails_soft(monkeypatch) -> None:
    monkeypatch.delenv("THREADS_DISCOVERY_ACCESS_TOKEN", raising=False)
    result = ThreadsGraphPublicDiscoveryAdapter().discover_profile(SOURCE, limit=5)
    assert result.status == "BLOCKED"
    assert result.reason == "AUTH_REQUIRED:threads_profile_discovery"
    assert result.data == []


def test_graph_documented_response_is_bounded_and_normalized() -> None:
    calls = []

    def loader(url, headers):
        calls.append((url, set(headers)))
        if "profile_lookup" in url:
            return {"id": "profile-1", "username": "me01_lsm"}
        return {"data": [graph_row(), graph_row(id="2", permalink="https://www.threads.com/@me01_lsm/post/DEF456")]}

    adapter = ThreadsGraphPublicDiscoveryAdapter(loader, token_loader=lambda: "runtime-secret")
    result = adapter.discover_profile(SOURCE, limit=1)
    assert result.status == "PASS"
    assert len(result.data or []) == 1
    assert result.data[0].media_items[0].media_type == "video"
    assert "limit=1" in calls[1][0]
    assert all("runtime-secret" not in url for url, _ in calls)


def test_graph_author_mismatch_is_rejected() -> None:
    try:
        normalize_graph_post(SOURCE, graph_row(username="someone_else"))
    except ValueError as exc:
        assert str(exc) == "threads_author_mismatch"
    else:
        raise AssertionError("author mismatch must fail closed")


def test_graph_keyword_search_is_bounded_and_author_scoped() -> None:
    def loader(url, headers):
        assert "keyword_search" in url
        assert "search_type=RECENT" in url
        assert "limit=2" in url
        return {"data": [graph_row(), graph_row(username="other", id="2", permalink="https://www.threads.com/@other/post/XYZ789")]}

    result = ThreadsGraphPublicDiscoveryAdapter(loader, token_loader=lambda: "runtime-secret").search_posts(
        SOURCE, "配信", limit=2
    )
    assert result.status == "PASS"
    assert len(result.data or []) == 1
    assert result.metadata["rejected_author_count"] == 1


def test_quote_or_repost_never_inherits_media_permission() -> None:
    post = normalize_graph_post(SOURCE, graph_row(is_quote_post=True, quoted_post={"id": "other"}))
    assert post.original_post_text
    assert post.media_items == ()
    assert post.detail_status == "PARTIAL"


def test_oembed_accepts_individual_post_and_not_thumbnail_as_video() -> None:
    payload = {
        "author_name": "me01_lsm",
        "author_url": "https://www.threads.com/@me01_lsm",
        "provider_name": "Threads",
        "title": "配信の継続は、無理のない時間設計から。",
        "thumbnail_url": "https://cdn.example/not-video.jpg",
        "html": "<blockquote><p>配信の継続は、無理のない時間設計から。</p></blockquote>",
    }
    adapter = ThreadsOEmbedDetailAdapter(lambda url, headers: payload)
    result = adapter.fetch_url(SOURCE, "https://threads.net/@me01_lsm/post/ABC123/")
    assert result.status == "PASS"
    assert result.data.canonical_post_url == "https://www.threads.com/@me01_lsm/post/ABC123"
    assert result.data.media_items == ()


def test_oembed_only_explicit_video_element_is_physical_video() -> None:
    payload = {
        "author_name": "me01_lsm",
        "author_url": "https://www.threads.com/@me01_lsm",
        "html": "<blockquote><p>本文</p><video poster='https://cdn.example/thumb.jpg'><source src='https://cdn.example/post.mp4'></video></blockquote>",
    }
    result = ThreadsOEmbedDetailAdapter(lambda url, headers: payload).fetch_url(
        SOURCE, "https://www.threads.com/@me01_lsm/post/ABC123"
    )
    assert len(result.data.media_items) == 1
    assert result.data.media_items[0].original_media_url == "https://cdn.example/post.mp4"


def test_search_discovery_is_bounded_deduped_and_wrong_author_rejected() -> None:
    page = """
      <a href='https://www.threads.com/@me01_lsm/post/ABC123'>ok</a>
      <a href='https://www.threads.com/@other/post/BAD123'>bad</a>
      <a href='https://www.threads.com/@me01_lsm/post/ABC123?x=1'>duplicate</a>
      <a href='https://www.threads.com/@me01_lsm/post/DEF456'>ok2</a>
    """
    assert extract_search_candidates(page, "me01_lsm", limit=1) == [
        "https://www.threads.com/@me01_lsm/post/ABC123"
    ]

    detail = ThreadsOEmbedDetailAdapter(
        lambda url, headers: {
            "author_name": "me01_lsm",
            "author_url": "https://www.threads.com/@me01_lsm",
            "title": "初見さんが入りやすい一言を決めておく。",
            "html": "<blockquote><p>初見さんが入りやすい一言を決めておく。</p></blockquote>",
        }
    )
    result = ThreadsSearchIndexAdapter(lambda url: page, detail).discover_profile(SOURCE, limit=5)
    assert result.status == "PASS"
    assert len(result.data or []) == 2
    assert result.metadata == {"candidate_count": 2, "rejected_count": 0, "bounded_limit": 5}


def test_oembed_rejects_profile_url_and_mismatched_author() -> None:
    adapter = ThreadsOEmbedDetailAdapter(lambda url, headers: {})
    profile = adapter.fetch_url(SOURCE, "https://www.threads.com/@me01_lsm")
    mismatch = adapter.fetch_url(SOURCE, "https://www.threads.com/@other/post/ABC123")
    assert profile.status == "BLOCKED"
    assert mismatch.reason == "threads_author_mismatch"


def test_short_oembed_url_requires_author_evidence() -> None:
    adapter = ThreadsOEmbedDetailAdapter(
        lambda url, headers: {"title": "本文", "html": "<blockquote><p>本文</p></blockquote>"}
    )
    result = adapter.fetch_url(SOURCE, "https://www.threads.com/t/ABC123")
    assert result.status == "FAILED"
    assert result.reason == "threads_author_unverified"
