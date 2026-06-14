"""
reference/fetchers - Source Fetcher Adapter package（Phase 9）

APIなし方針: yt-dlp / tiktok-to-ytdlp / youtube-transcript-api /
browser_export / manual_json を使うアダプター群。
実取得には --fetch --confirm-fetch が必要。
実downloadには --download --confirm-download が必要。
"""
from .fetcher_registry import FetcherRegistry, get_fetcher
from .base_fetcher import BaseFetcher, FetchResult, RawSourceItem

__all__ = ["BaseFetcher", "FetchResult", "RawSourceItem", "FetcherRegistry", "get_fetcher"]
