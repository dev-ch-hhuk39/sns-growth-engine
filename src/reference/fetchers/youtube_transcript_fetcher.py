"""
youtube_transcript_fetcher.py - YouTube Transcript Fetcher（Phase 9）

youtube-transcript-api を使って字幕/自動字幕を取得する。
実download禁止。transcript取得も confirm_fetch が必要。
取得できない場合は NOT_READY_TRANSCRIPT を返す。
"""
from __future__ import annotations

from typing import Any

from .base_fetcher import BaseFetcher, FetchResult, RawSourceItem, _now_jst


def _check_youtube_transcript() -> bool:
    try:
        import youtube_transcript_api  # noqa: F401
        return True
    except ImportError:
        return False


def _extract_video_id(url: str) -> str:
    import re
    patterns = [
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"youtube\.com/watch\?.*v=([A-Za-z0-9_-]{11})",
        r"youtube\.com/shorts/([A-Za-z0-9_-]{11})",
        r"youtube\.com/embed/([A-Za-z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return ""


class YoutubeTranscriptFetcher(BaseFetcher):
    """youtube-transcript-api で YouTube 字幕を取得する。

    transcript_required=True の source に対して使う。
    transcript は video_understanding へ渡す。
    """

    adapter_name = "youtube_transcript"
    supported_platforms = ["youtube", "youtube_shorts"]

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
        video_urls: list[str] | None = None,
        preferred_languages: list[str] | None = None,
    ) -> FetchResult:
        source_id = source.get("source_id", "")
        preferred_languages = preferred_languages or ["ja", "en"]

        if mock:
            items = [
                self._make_mock_transcript(source, target_account_id, i)
                for i in range(min(2, max_items))
            ]
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="OK",
                items=items,
                message=f"MOCK: YouTube transcript {len(items)}件のモックを返します。",
                mock=True,
                dry_run=dry_run,
            )

        if not confirm_fetch:
            return self._blocked(
                source,
                "--confirm-fetch が指定されていません。transcript取得をブロックします。",
            )

        if not _check_youtube_transcript():
            return self._not_installed(
                source,
                "youtube-transcript-api (pip install youtube-transcript-api)",
            )

        urls_to_fetch = video_urls or [source.get("source_url", "")]
        urls_to_fetch = [u for u in urls_to_fetch if u]

        if not urls_to_fetch:
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="NOT_READY",
                message="取得対象の video_url が未設定です。",
            )

        items: list[RawSourceItem] = []
        errors: list[str] = []

        for i, url in enumerate(urls_to_fetch[:max_items]):
            video_id = _extract_video_id(url)
            if not video_id:
                errors.append(f"動画IDを抽出できません: {url}")
                continue

            try:
                transcript_text, lang = self._fetch_transcript(video_id, preferred_languages)
            except Exception as e:
                errors.append(f"{video_id}: {e}")
                continue

            item = RawSourceItem(
                source_id=source.get("source_id", ""),
                source_platform="youtube",
                source_handle=source.get("source_handle", ""),
                source_url=source.get("source_url", url),
                target_account_id=target_account_id,
                fetch_adapter=self.adapter_name,
                fetch_method="youtube_transcript",
                item_type="video",
                post_id=video_id,
                post_url=url,
                transcript=transcript_text,
                fetched_at=_now_jst(),
                rights_status=source.get("rights_policy", "reference_only"),
                reuse_policy=source.get("reuse_policy", "reference_only"),
                media_policy=source.get("media_policy", "do_not_download"),
                raw_payload_compact={"language": lang, "video_id": video_id},
                mock=False,
            )
            items.append(item)

        if not items and errors:
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="NOT_READY_TRANSCRIPT",
                message=f"transcript 取得不可: {'; '.join(errors[:3])}",
                warn="字幕が無効、または非公開の動画の可能性があります。",
            )

        return FetchResult(
            adapter=self.adapter_name,
            source_id=source_id,
            status="OK",
            items=items,
            message=f"transcript {len(items)}件取得。エラー {len(errors)}件。",
            warn="; ".join(errors[:2]) if errors else "",
            mock=False,
            dry_run=dry_run,
        )

    def _fetch_transcript(
        self, video_id: str, preferred_languages: list[str]
    ) -> tuple[str, str]:
        from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled

        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        except (NoTranscriptFound, TranscriptsDisabled) as e:
            raise RuntimeError(f"transcript 利用不可: {e}")

        # 優先言語順に取得試行
        for lang in preferred_languages:
            try:
                t = transcript_list.find_transcript([lang])
                segments = t.fetch()
                text = " ".join(s["text"] for s in segments)
                return text, lang
            except Exception:
                continue

        # 自動字幕を翻訳して取得
        try:
            t = transcript_list.find_generated_transcript(["ja", "en"])
            segments = t.fetch()
            text = " ".join(s["text"] for s in segments)
            return text, f"{t.language_code}_auto"
        except Exception as e:
            raise RuntimeError(f"自動字幕も取得不可: {e}")

    def _make_mock_transcript(
        self, source: dict, target_account_id: str, index: int
    ) -> RawSourceItem:
        item = self._make_mock_item(source, target_account_id, index)
        item.fetch_adapter = self.adapter_name
        item.fetch_method = "youtube_transcript"
        item.transcript = (
            f"【モック transcript {index+1}】"
            "今日はみなさんに大切なことをお伝えしたいと思います。"
            "このチャンネルでは毎日役立つ情報をお届けしています。"
            "チャンネル登録よろしくお願いします。"
            "今回のテーマは非常に重要で多くの方が悩んでいることです。"
        )
        item.raw_payload_compact = {"language": "ja", "video_id": f"mock_{index:03d}"}
        return item
