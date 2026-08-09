from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from generation.multiplatform_media_router import merge_designated_sources, normalize_platform, platform_counts, provider_chain


def test_platform_detection_and_provider_chains() -> None:
    assert normalize_platform(url="https://www.tiktok.com/@a/video/1") == "tiktok"
    assert normalize_platform(url="https://www.threads.com/@a/post/abc") == "threads"
    assert normalize_platform(url="https://x.com/a/status/1") == "x"
    assert normalize_platform(url="https://youtu.be/abc") == "youtube"
    assert provider_chain("youtube") == ("yt_dlp",)
    assert provider_chain("tiktok")[:2] == ("direct_http", "gallery_dl")
    assert provider_chain("threads") == ("direct_http", "threads_public_router")
    assert "gallery_dl" in provider_chain("x")


def test_merge_designated_sources_is_cross_platform_and_sheet_preferred() -> None:
    config = [
        {"source_id":"s1","target_account_ids":["night_scout"],"source_platform":"youtube","source_url":"https://youtube.com/@a","active":False},
        {"source_id":"s2","target_account_ids":["night_scout"],"source_platform":"tiktok","source_url":"https://www.tiktok.com/@b","active":False},
        {"source_id":"s3","target_account_ids":["night_scout"],"source_platform":"threads","source_url":"https://www.threads.com/@c","active":False},
        {"source_id":"s4","target_account_ids":["night_scout"],"source_platform":"x","source_url":"https://x.com/d","active":False},
    ]
    sheet = [{"source_id":"s2","target_account_id":"night_scout","platform":"tiktok","source_url":"https://www.tiktok.com/@b","active":"true"}]
    rows = merge_designated_sources("night_scout", sheet, config)
    assert len(rows) == 4
    assert platform_counts(rows) == {"threads":1,"tiktok":1,"x":1,"youtube":1}
    assert rows[0]["source_id"] == "s2"  # active Sheet row first
