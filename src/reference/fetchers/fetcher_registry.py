"""
fetcher_registry.py - Fetcher Adapter Registry（Phase 9）

collection_method / source_platform から適切な Fetcher を返す。
"""
from __future__ import annotations

from typing import Any

from .base_fetcher import BaseFetcher
from .json_import_fetcher import JsonImportFetcher
from .yt_dlp_fetcher import YtDlpFetcher
from .tiktok_to_ytdlp_fetcher import TiktokToYtdlpFetcher
from .agent_reach_fetcher import AgentReachFetcher
from .last30days_fetcher import Last30DaysFetcher
from .youtube_transcript_fetcher import YoutubeTranscriptFetcher
from .browser_export_fetcher import BrowserExportFetcher


_REGISTRY: dict[str, BaseFetcher] = {
    "json_import": JsonImportFetcher(),
    "manual_json": JsonImportFetcher(),
    "manual_csv": JsonImportFetcher(),
    "manual_url": JsonImportFetcher(),
    "yt_dlp": YtDlpFetcher(),
    "tiktok_to_ytdlp": TiktokToYtdlpFetcher(),
    "agent_reach": AgentReachFetcher(),
    "last30days_skill": Last30DaysFetcher(),
    "youtube_transcript": YoutubeTranscriptFetcher(),
    "browser_export": BrowserExportFetcher(),
    "api_disabled": JsonImportFetcher(),  # fallback to manual
    "scrape_disallowed": JsonImportFetcher(),  # returns BLOCKED
}

_PLATFORM_DEFAULT: dict[str, str] = {
    "youtube": "yt_dlp",
    "youtube_playlist": "yt_dlp",
    "youtube_streams": "yt_dlp",
    "youtube_shorts": "yt_dlp",
    "tiktok": "tiktok_to_ytdlp",
    "x": "agent_reach",
    "threads": "browser_export",
    "instagram_reels": "browser_export",
    "note": "manual_url",
    "query": "last30days_skill",
}


class FetcherRegistry:
    """collection_method → Fetcher を解決する。"""

    def get(self, collection_method: str, platform: str = "") -> BaseFetcher:
        if collection_method == "scrape_disallowed":
            return _REGISTRY["scrape_disallowed"]
        fetcher = _REGISTRY.get(collection_method)
        if fetcher:
            return fetcher
        # platform デフォルト
        default_method = _PLATFORM_DEFAULT.get(platform, "json_import")
        return _REGISTRY.get(default_method, _REGISTRY["json_import"])

    def list_adapters(self) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result = []
        for name, fetcher in _REGISTRY.items():
            cls = fetcher.__class__.__name__
            if cls not in seen:
                seen.add(cls)
                result.append({
                    "adapter": fetcher.adapter_name,
                    "class": cls,
                    "supported_platforms": fetcher.supported_platforms,
                    "collection_methods": [k for k, v in _REGISTRY.items() if v is fetcher],
                })
        return result


def get_fetcher(collection_method: str, platform: str = "") -> BaseFetcher:
    return FetcherRegistry().get(collection_method, platform)
