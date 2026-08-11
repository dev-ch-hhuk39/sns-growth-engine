from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from acquisition.factory import build_router
from acquisition.models import validate_source_post
from acquisition.router import BackendFailure
from acquisition.x_gallerydl import XGalleryDlProfileAdapter


def test_bounded_gallery_dl_normalizes_only_individual_posts(monkeypatch):
    adapter = XGalleryDlProfileAdapter()
    monkeypatch.setattr("acquisition.x_gallerydl.shutil.which", lambda _: "/usr/bin/gallery-dl")
    rows = [
        {"tweet_id": "123", "tweet_content": "reference text", "url": "https://cdn.example/1.jpg", "post_url": "https://x.com/meg_lsm/status/123", "num": 1},
        {"tweet_id": "123", "tweet_content": "reference text", "url": "https://cdn.example/2.jpg", "post_url": "https://x.com/meg_lsm/status/123", "num": 2},
    ]
    captured = {}
    def fake_run(command, **kwargs):
        captured["command"] = command
        return SimpleNamespace(returncode=0, stdout="\n".join(json.dumps(row) for row in rows), stderr="")
    monkeypatch.setattr("acquisition.x_gallerydl.subprocess.run", fake_run)

    posts = adapter.acquire({"source_id": "s", "source_url": "https://x.com/meg_lsm", "target_account_ids": ["liver_manager"], "x_read_only": True}, limit=99)

    command = captured["command"]
    assert command[0] == "gallery-dl"
    assert "--config-ignore" in command
    assert "--no-input" in command
    assert "--no-download" in command
    assert "--resolve-json" in command
    assert command[command.index("--range") + 1] == "1-20"
    assert command[-1] == "https://x.com/meg_lsm"
    assert len(posts) == 1
    assert posts[0].canonical_post_url == "https://x.com/meg_lsm/status/123"
    assert [item.media_index for item in posts[0].media_items] == [0, 1]
    assert not validate_source_post(posts[0])


def test_x_gallery_dl_requires_explicit_bounded_source():
    with pytest.raises(BackendFailure, match="x_read_only_not_approved"):
        XGalleryDlProfileAdapter().acquire({"source_url": "https://x.com/example"}, limit=1)


def test_x_gallery_dl_empty_result_requires_manual_recovery(monkeypatch):
    adapter = XGalleryDlProfileAdapter()
    monkeypatch.setattr("acquisition.x_gallerydl.shutil.which", lambda _: "/usr/bin/gallery-dl")
    monkeypatch.setattr("acquisition.x_gallerydl.subprocess.run", lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""))
    with pytest.raises(BackendFailure, match="browser_export_or_manual_json_required"):
        adapter.acquire({"source_url": "https://x.com/meg_lsm", "x_read_only": True}, limit=1)


def test_x_gallery_dl_reports_auth_required_without_cookie_extraction(monkeypatch):
    adapter = XGalleryDlProfileAdapter()
    monkeypatch.setattr("acquisition.x_gallerydl.shutil.which", lambda _: "/usr/bin/gallery-dl")
    payload = [[-1, {"error": "AuthRequired", "message": "authenticated cookies needed"}]]
    monkeypatch.setattr(
        "acquisition.x_gallerydl.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr=""),
    )
    with pytest.raises(BackendFailure, match="auth_required_explicit_cookie_required"):
        adapter.acquire({"source_url": "https://x.com/meg_lsm", "x_read_only": True}, limit=1)


def test_factory_registers_x_gallery_dl_route():
    router = build_router()
    assert router.routes["x.profile_posts"].primary == "x_gallery_dl"
    assert router.adapters["x_gallery_dl"].backend_name == "x_gallery_dl"
