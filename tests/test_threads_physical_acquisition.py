from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from generation import video_source_acquirer as acquirer  # noqa: E402


def _permission():
    return {
        "source_id": "src_ns_threads_owner_001",
        "source_handle": "@approved.owner",
        "permission_status": "approved",
        "rights_status": "approved_creator_clip",
        "usage_mode": "direct_and_clip",
        "evidence_type": "owner_attestation",
        "evidence_reference": "owner decision",
        "approved_by": "owner",
        "approved_at": "2026-08-24T00:00:00+00:00",
        "allowed_accounts": "night_scout",
        "allow_download": "true",
        "allow_cut": "true",
    }


def _candidate(handle="approved.owner"):
    return {
        "source_id": "src_ns_threads_owner_001",
        "platform": "threads",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "canonical_post_url": f"https://www.threads.com/@{handle}/post/ABC123",
        "original_media_url": "https://scontent.cdninstagram.com/video.mp4",
        "source_handle": f"@{handle}",
    }


class _Response:
    headers = {"Content-Length": "10"}

    def __init__(self):
        self._chunks = [b"video-data", b""]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return "https://scontent.cdninstagram.com/video.mp4"

    def read(self, _size):
        return self._chunks.pop(0)


def test_threads_direct_physical_download_requires_permission_and_same_author(tmp_path, monkeypatch):
    monkeypatch.setattr(acquirer, "_validate_public_http_url", lambda _url: None)
    monkeypatch.setattr(acquirer, "urlopen", lambda *_args, **_kwargs: _Response())
    monkeypatch.setattr(acquirer, "_has_video_stream", lambda path: path.read_bytes() == b"video-data")
    path = acquirer.acquire_authorized_public_source(
        _candidate(),
        {"source_id": "src_ns_threads_owner_001", "platform": "threads"},
        cache_root=tmp_path,
        account_id="night_scout",
        source_video_id="sv_threads_1",
        permission_rows=[_permission()],
        registered_source={
            "source_handle": "@approved.owner",
            "source_url": "https://www.threads.com/@approved.owner",
        },
    )
    assert path.read_bytes() == b"video-data"
    assert path.name == "sv_threads_1-video.mp4"


def test_threads_direct_physical_download_blocks_cross_author(tmp_path):
    candidate = _candidate("different.owner")
    candidate["source_handle"] = "@approved.owner"
    with pytest.raises(PermissionError, match="author_does_not_match"):
        acquirer.acquire_authorized_public_source(
            candidate,
            {"source_id": "src_ns_threads_owner_001", "platform": "threads"},
            cache_root=tmp_path,
            account_id="night_scout",
            source_video_id="sv_threads_2",
            permission_rows=[_permission()],
            registered_source={
                "source_handle": "@approved.owner",
                "source_url": "https://www.threads.com/@approved.owner",
            },
        )


def test_threads_direct_media_rejects_untrusted_cdn():
    candidate = _candidate()
    candidate["original_media_url"] = "https://untrusted.example/video.mp4"
    assert acquirer._threads_direct_media_url(candidate, {}) == ""
