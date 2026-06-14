"""
tiktok_to_ytdlp_fetcher.py - TikTok → yt-dlp URL変換 Fetcher（Phase 9）

tiktok-to-ytdlp でTikTokアカウント/音源URLをyt-dlp URLリストに変換し、
YtDlpFetcherへ渡す。実取得・実downloadは confirm が必要。
未インストールなら NOT_INSTALLED を返す。
"""
from __future__ import annotations

import subprocess
from typing import Any

from .base_fetcher import BaseFetcher, FetchResult, RawSourceItem, _now_jst
from .yt_dlp_fetcher import YtDlpFetcher


def _check_tiktok_to_ytdlp() -> bool:
    try:
        result = subprocess.run(
            ["tiktok-to-ytdlp", "--help"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


class TiktokToYtdlpFetcher(BaseFetcher):
    """tiktok-to-ytdlp でURLリストを生成し、yt-dlp fetcher で metadata 取得する。"""

    adapter_name = "tiktok_to_ytdlp"
    supported_platforms = ["tiktok"]

    def __init__(self):
        self._yt_dlp = YtDlpFetcher()

    def fetch(
        self,
        source: dict[str, Any],
        *,
        target_account_id: str = "",
        mock: bool = True,
        dry_run: bool = True,
        confirm_fetch: bool = False,
        confirm_download: bool = False,
        max_items: int = 10,
    ) -> FetchResult:
        source_id = source.get("source_id", "")

        if mock:
            items = [
                self._make_mock_item(source, target_account_id, i)
                for i in range(min(3, max_items))
            ]
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="OK",
                items=items,
                message=f"MOCK: TikTok {len(items)}件のモックデータを返します。",
                mock=True,
                dry_run=dry_run,
                warn="tiktok-to-ytdlp は TikTok 仕様変更の影響を受ける可能性があります。",
            )

        if not confirm_fetch:
            return self._blocked(
                source,
                "--confirm-fetch が指定されていません。実取得をブロックします。",
            )

        if not _check_tiktok_to_ytdlp():
            return self._not_installed(source, "tiktok-to-ytdlp")

        source_url = source.get("source_url", "")
        if not source_url:
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="NOT_READY",
                message="source_url が未設定です。",
            )

        # URLリスト生成
        try:
            urls = self._get_video_urls(source_url, max_items)
        except Exception as e:
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="WARN",
                message=f"tiktok-to-ytdlp URL生成エラー（fallback: なし）: {e}",
                warn="TikTok 仕様変更の可能性があります。",
            )

        if not urls:
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="NOT_READY",
                message="URLリストが空でした。TikTok 仕様変更の可能性があります。",
            )

        all_items: list[RawSourceItem] = []
        errors: list[str] = []
        for url in urls[:max_items]:
            url_source = dict(source)
            url_source["source_url"] = url
            result = self._yt_dlp.fetch(
                url_source,
                target_account_id=target_account_id,
                mock=False,
                dry_run=dry_run,
                confirm_fetch=confirm_fetch,
                confirm_download=confirm_download,
                max_items=1,
            )
            if result.status == "OK":
                all_items.extend(result.items)
            else:
                errors.append(f"{url}: {result.message}")

        return FetchResult(
            adapter=self.adapter_name,
            source_id=source_id,
            status="OK" if all_items else "WARN",
            items=all_items,
            message=f"TikTok {len(all_items)}件取得。エラー {len(errors)}件。",
            warn="; ".join(errors[:3]) if errors else "",
            mock=False,
            dry_run=dry_run,
        )

    def _get_video_urls(self, profile_url: str, max_items: int) -> list[str]:
        cmd = ["tiktok-to-ytdlp", profile_url, "--limit", str(max_items)]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr[:300])

        urls = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line.startswith("https://"):
                urls.append(line)
        return urls
