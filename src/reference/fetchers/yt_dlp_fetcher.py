"""
yt_dlp_fetcher.py - yt-dlp based Fetcher（Phase 9）

YouTube / TikTok / YouTube Shorts の metadata-only 取得。
実取得には confirm_fetch=True が必要。
実downloadには confirm_download=True が必要。
yt-dlp 未インストールなら NOT_INSTALLED を返す。
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from .base_fetcher import BaseFetcher, FetchResult, RawSourceItem, _now_jst


def _check_ytdlp() -> bool:
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _platform_from_url(url: str) -> str:
    url_l = url.lower()
    if "youtu.be" in url_l or "youtube.com" in url_l:
        if "shorts" in url_l:
            return "youtube_shorts"
        return "youtube"
    if "tiktok.com" in url_l:
        return "tiktok"
    return "unknown"


class YtDlpFetcher(BaseFetcher):
    """yt-dlp を使って YouTube / TikTok / Shorts の metadata を取得する。"""

    adapter_name = "yt_dlp"
    supported_platforms = ["youtube", "youtube_shorts", "tiktok"]

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
        source_url = source.get("source_url", "")
        platform = source.get("source_platform", _platform_from_url(source_url))

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
                message=f"MOCK: {len(items)}件のモックメタデータを返します。",
                mock=True,
                dry_run=dry_run,
            )

        if not confirm_fetch:
            return self._blocked(
                source,
                "--confirm-fetch が指定されていません。実取得をブロックします。"
            )

        if not source_url:
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="NOT_READY",
                message="source_url が未設定です。",
            )

        if not _check_ytdlp():
            return self._not_installed(source, "yt-dlp")

        # metadata-only 取得（--no-download）
        try:
            raw_items = self._fetch_metadata(source_url, max_items)
        except Exception as e:
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="ERROR",
                message=f"yt-dlp 実行エラー: {e}",
            )

        items = [
            self._normalize_ytdlp(r, source, target_account_id, i)
            for i, r in enumerate(raw_items)
        ]

        return FetchResult(
            adapter=self.adapter_name,
            source_id=source_id,
            status="OK",
            items=items,
            message=f"yt-dlp metadata {len(items)}件取得完了。",
            mock=False,
            dry_run=dry_run,
        )

    def _fetch_metadata(self, url: str, max_items: int) -> list[dict]:
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--no-download",
            "--no-warnings",
            "--flat-playlist",
        ]
        if max_items:
            cmd += ["--playlist-end", str(max_items)]
        cmd.append(url)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            stderr = result.stderr[:500] if result.stderr else ""
            raise RuntimeError(f"yt-dlp 終了コード {result.returncode}: {stderr}")

        items = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return items

    def _normalize_ytdlp(
        self,
        raw: dict[str, Any],
        source: dict,
        target_account_id: str,
        index: int,
    ) -> RawSourceItem:
        platform = _platform_from_url(raw.get("webpage_url", source.get("source_url", "")))
        if platform == "unknown":
            platform = source.get("source_platform", "youtube")

        thumbnails = raw.get("thumbnails", [])
        thumbnail_url = ""
        if thumbnails and isinstance(thumbnails, list):
            thumbnail_url = thumbnails[-1].get("url", "")
        elif raw.get("thumbnail"):
            thumbnail_url = raw["thumbnail"]

        subtitles = raw.get("subtitles", {})
        auto_captions = raw.get("automatic_captions", {})
        has_transcript = bool(subtitles or auto_captions)

        return RawSourceItem(
            source_id=source.get("source_id", ""),
            source_platform=platform,
            source_handle=source.get("source_handle", f"@{raw.get('uploader', '')}"),
            source_url=source.get("source_url", ""),
            target_account_id=target_account_id,
            fetch_adapter=self.adapter_name,
            fetch_method="yt_dlp_metadata",
            item_type="video",
            post_id=str(raw.get("id", f"yt_{index}")),
            post_url=str(raw.get("webpage_url", raw.get("url", ""))),
            author_handle=f"@{raw.get('uploader', '')}",
            author_name=str(raw.get("uploader", "")),
            text=str(raw.get("title", "")),
            title=str(raw.get("title", "")),
            description=str(raw.get("description", ""))[:2000],
            hashtags=[
                t.get("term", "") for t in raw.get("tags", [])
                if isinstance(t, dict) and t.get("term", "").startswith("#")
            ] if isinstance(raw.get("tags"), list) else [],
            posted_at=_format_date(raw.get("upload_date", "")),
            like_count=int(raw.get("like_count") or 0),
            view_count=int(raw.get("view_count") or 0),
            follower_count=int(raw.get("channel_follower_count") or 0),
            thumbnail_url=thumbnail_url,
            duration_seconds=float(raw.get("duration") or 0) or None,
            transcript=None,  # transcript は youtube_transcript_fetcher が担当
            raw_payload_compact={
                "id": raw.get("id"),
                "extractor": raw.get("extractor"),
                "upload_date": raw.get("upload_date"),
                "has_subtitles": has_transcript,
                "chapters": len(raw.get("chapters") or []),
            },
            fetched_at=_now_jst(),
            rights_status=source.get("rights_policy", "reference_only"),
            reuse_policy=source.get("reuse_policy", "reference_only"),
            media_policy=source.get("media_policy", "do_not_download"),
            fetch_warn="transcript_not_fetched: --transcript が必要です" if has_transcript else "",
        )


def _format_date(d: str) -> str:
    if not d or len(d) < 8:
        return ""
    try:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}T00:00:00+09:00"
    except Exception:
        return ""
