from __future__ import annotations
import sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from generation.video_source_acquirer import (
    find_cached_source,
    is_download_authorized,
    resolve_source_url,
    _validate_public_http_url,
)


def test_authorized_creator_clip_is_downloadable() -> None:
    row = {"rights_status": "approved_creator_clip", "media_reuse_risk": "low"}
    assert is_download_authorized(row) is True


def test_unknown_or_high_risk_is_not_download_authorized() -> None:
    assert is_download_authorized({"rights_status": "unknown", "media_reuse_risk": "low"}) is False
    assert is_download_authorized({"rights_status": "allowed", "media_reuse_risk": "high"}) is False


def test_resolve_source_url_prefers_candidate_then_source() -> None:
    assert resolve_source_url({"source_video_url": "https://example.com/a"}, {"url": "https://example.com/b"}).endswith("/a")
    assert resolve_source_url({}, {"url": "https://example.com/b"}).endswith("/b")


def test_private_source_urls_are_blocked() -> None:
    with pytest.raises(ValueError):
        _validate_public_http_url("http://127.0.0.1/video.mp4")


def test_cache_lookup_is_deterministic(tmp_path) -> None:
    directory = tmp_path / "night_scout"
    directory.mkdir()
    target = directory / "sv-1.mp4"
    target.write_bytes(b"video")
    assert find_cached_source(tmp_path, "night_scout", "sv-1") == target


def test_cache_can_require_real_video_stream(tmp_path, monkeypatch) -> None:
    import generation.video_source_acquirer as acq
    directory = tmp_path / "night_scout"
    directory.mkdir()
    audio = directory / "sv-2.mp4"
    visual = directory / "sv-2-video.mp4"
    audio.write_bytes(b"audio")
    visual.write_bytes(b"video")

    monkeypatch.setattr(acq, "_has_video_stream", lambda path: path.name.endswith("-video.mp4"))
    assert acq.find_cached_source(tmp_path, "night_scout", "sv-2", require_video=True) == visual
