from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from generation import video_source_acquirer as acquirer  # noqa: E402


def _permission():
    return {
        "source_id": "src_lm_tt_user_001",
        "source_handle": "@allowed",
        "permission_status": "approved",
        "rights_status": "approved_creator_clip",
        "usage_mode": "direct_and_clip",
        "evidence_type": "owner_attestation",
        "evidence_reference": "owner decision",
        "approved_by": "owner",
        "approved_at": "2026-08-11T00:00:00+00:00",
        "allowed_accounts": "liver_manager",
        "allow_download": "true",
        "allow_cut": "true",
    }


def _candidate(handle="allowed"):
    return {
        "source_id": "src_lm_tt_user_001",
        "platform": "tiktok",
        "rights_status": "approved_creator_clip",
        "permission_status": "approved",
        "canonical_post_url": f"https://www.tiktok.com/@{handle}/video/7649682547588254994",
        "original_media_url": "https://v45.tiktokcdn.com/video.mp4",
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
        return "https://v45.tiktokcdn.com/video.mp4"

    def read(self, _size):
        return self._chunks.pop(0)


def test_tiktok_direct_physical_download_requires_permission_and_same_author(tmp_path, monkeypatch):
    monkeypatch.setattr(acquirer, "_validate_public_http_url", lambda _url: None)
    monkeypatch.setattr(acquirer, "urlopen", lambda *_args, **_kwargs: _Response())
    monkeypatch.setattr(acquirer, "_has_video_stream", lambda path: path.read_bytes() == b"video-data")
    path = acquirer.acquire_authorized_public_source(
        _candidate(),
        {"source_id": "src_lm_tt_user_001", "platform": "tiktok", "source_url": "https://www.tiktok.com/@allowed"},
        cache_root=tmp_path,
        account_id="liver_manager",
        source_video_id="sv_tiktok_1",
        permission_rows=[_permission()],
        registered_source={"source_handle": "@allowed", "source_url": "https://www.tiktok.com/@allowed"},
    )
    assert path.read_bytes() == b"video-data"
    assert path.name == "sv_tiktok_1-video.mp4"


def test_tiktok_direct_physical_download_blocks_cross_author(tmp_path):
    candidate = _candidate("different")
    candidate["source_handle"] = "@allowed"
    with pytest.raises(PermissionError, match="author_does_not_match"):
        acquirer.acquire_authorized_public_source(
            candidate,
            {"source_id": "src_lm_tt_user_001", "platform": "tiktok", "source_url": "https://www.tiktok.com/@allowed"},
            cache_root=tmp_path,
            account_id="liver_manager",
            source_video_id="sv_tiktok_2",
            permission_rows=[_permission()],
            registered_source={"source_handle": "@allowed", "source_url": "https://www.tiktok.com/@allowed"},
        )


def test_tiktok_direct_media_rejects_non_tiktok_cdn():
    candidate = _candidate()
    candidate["original_media_url"] = "https://untrusted.example/video.mp4"
    assert acquirer._tiktok_direct_media_url(candidate, {}) == ""
