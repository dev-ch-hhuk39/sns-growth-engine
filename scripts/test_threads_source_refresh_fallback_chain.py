#!/usr/bin/env python3
"""A backend 404 falls through; parent/author/media-child mismatches do not."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "src")]

import ingest_direct_reference_media as ingest  # noqa: E402
from acquisition.router import BackendFailure  # noqa: E402
from acquisition.threads_cli import _raw_graph_post  # noqa: E402
from acquisition.threads_public import ThreadsPublicHttpAdapter  # noqa: E402

parent = "https://www.threads.com/@approved/post/ABC123"
source = {"source_id": "src_threads", "source_url": "https://www.threads.com/@approved", "target_account_id": "night_scout"}
resolved_post = ThreadsPublicHttpAdapter(html_loader=lambda _url: '<meta property="og:video" content="https://cdninstagram.com/fresh.mp4">').acquire_post(source, parent)
post = {**source, "profile_url": source["source_url"], "canonical_post_url": parent,
        "source_post_id": resolved_post.source_post_id, "author_handle": "approved"}
media = {"source_post_id": resolved_post.source_post_id, "canonical_post_url": parent, "media_index": "0", "media_type": "video"}

calls = []
class Backend404:
    def acquire_post(self, _source, _url):
        calls.append("404")
        raise BackendFailure("threads_post_application_404")

class ExactScreen:
    def acquire_post(self, _source, url):
        calls.append("screen")
        assert url == parent
        return resolved_post

old = (ingest.ThreadsCliPublicAdapter, ingest.ThreadsLoggedOutGraphQLAdapter,
       ingest.ThreadsPublicScreenAdapter, ingest.safe_https_url)
try:
    ingest.ThreadsCliPublicAdapter = Backend404
    ingest.ThreadsLoggedOutGraphQLAdapter = Backend404
    ingest.ThreadsPublicScreenAdapter = ExactScreen
    ingest.safe_https_url = lambda *_args, **_kwargs: True
    refreshed, backend = ingest.refresh_threads_media_url(post, media)
    assert refreshed == "https://cdninstagram.com/fresh.mp4"
    assert backend == "threads_public_http"
    assert calls == ["404", "404", "screen"]

    calls.clear()
    class IdentityMismatch:
        def acquire_post(self, _source, _url):
            calls.append("mismatch")
            raise BackendFailure("threads_post_author_mismatch")
    ingest.ThreadsCliPublicAdapter = IdentityMismatch
    try:
        ingest.refresh_threads_media_url(post, media)
    except RuntimeError as exc:
        assert "author_mismatch" in str(exc)
    else:
        raise AssertionError("identity mismatch must stop the chain")
    assert calls == ["mismatch"]
finally:
    (ingest.ThreadsCliPublicAdapter, ingest.ThreadsLoggedOutGraphQLAdapter,
     ingest.ThreadsPublicScreenAdapter, ingest.safe_https_url) = old

video = _raw_graph_post({"pk": "123", "code": "ABC123", "media_type": 2,
                         "video_versions": [{"url": "https://cdn.test/video.mp4"}],
                         "user": {"username": "approved"}})
assert video["media_types"] == ["video"]
carousel = _raw_graph_post({"pk": "456", "code": "DEF456", "media_type": 8,
                           "carousel_media": [
                               {"media_type": 1, "image_versions2": {"candidates": [{"url": "https://cdn.test/a.jpg"}]}},
                               {"media_type": 2, "video_versions": [{"url": "https://cdn.test/b.mp4"}]},
                           ], "user": {"username": "approved"}})
assert carousel["media_types"] == ["image", "video"]
print("PASS test_threads_source_refresh_fallback_chain.py")
