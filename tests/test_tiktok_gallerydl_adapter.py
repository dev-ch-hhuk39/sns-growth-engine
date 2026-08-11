from __future__ import annotations
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from acquisition.factory import build_router
from acquisition.tiktok_gallerydl import TikTokGalleryDlProfileAdapter


def test_gallery_dl_is_bounded_fallback_and_returns_individual_video(monkeypatch):
    adapter = TikTokGalleryDlProfileAdapter()
    monkeypatch.setattr("acquisition.tiktok_gallerydl.shutil.which", lambda _: "/usr/bin/gallery-dl")
    row = {"url": "https://cdn.example/video.mp4", "post_url": "https://www.tiktok.com/@allowed/video/123", "description": "配信の入口"}
    seen = {}
    def fake_run(command, **kwargs):
        seen["command"] = command
        return SimpleNamespace(returncode=0, stdout=json.dumps(row), stderr="")
    monkeypatch.setattr("acquisition.tiktok_gallerydl.subprocess.run", fake_run)
    posts = adapter.acquire({"source_id": "s", "source_platform": "tiktok", "source_url": "https://www.tiktok.com/@allowed", "target_account_ids": ["liver_manager"], "fetch_enabled": True}, limit=99)
    assert seen["command"][:4] == ["gallery-dl", "--dump-json", "--range", "1-20"]
    assert posts[0].canonical_post_url.endswith("/video/123")
    assert posts[0].media_items[0].media_index == 0


def test_router_uses_gallery_dl_without_playwright():
    route = build_router().routes["tiktok.profile_posts"]
    assert route.fallbacks == ("tiktok_gallery_dl",)
