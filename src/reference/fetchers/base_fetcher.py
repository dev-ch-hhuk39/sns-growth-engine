"""
base_fetcher.py - Source Fetcher 共通インターフェース（Phase 9）

APIなし方針:
  - 実取得には confirm_fetch=True が必須
  - 実downloadには confirm_download=True が必須
  - mock=True でモックデータを返す
  - 各adapterはこのクラスを継承して fetch() を実装する

禁止事項:
  - 実SNS API呼び出し
  - --confirm-fetch なしの実ネットワーク取得
  - --confirm-download なしのファイル保存
  - secret/cookie値の出力
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

JST = timezone(timedelta(hours=9))


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _new_id() -> str:
    return str(uuid.uuid4())[:12]


@dataclass
class RawSourceItem:
    """raw_source_items の1件。全adapterの共通出力形式。"""
    raw_item_id: str = field(default_factory=_new_id)
    source_id: str = ""
    source_platform: str = ""
    source_handle: str = ""
    source_url: str = ""
    target_account_id: str = ""
    fetch_adapter: str = ""
    fetch_method: str = ""
    item_type: str = "post"          # post / video / shorts / thread
    post_id: str = ""
    post_url: str = ""
    author_handle: str = ""
    author_name: str = ""
    text: str = ""
    title: str = ""
    description: str = ""
    hashtags: list[str] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    posted_at: str = ""
    like_count: int = 0
    reply_count: int = 0
    repost_count: int = 0
    quote_count: int = 0
    bookmark_count: int = 0
    impression_count: int = 0
    view_count: int = 0
    follower_count: int = 0
    image_urls: list[str] = field(default_factory=list)
    video_urls: list[str] = field(default_factory=list)
    thumbnail_url: str = ""
    duration_seconds: float | None = None
    transcript: str | None = None
    raw_payload_compact: dict[str, Any] = field(default_factory=dict)
    fetched_at: str = field(default_factory=_now_jst)
    rights_status: str = "reference_only"
    reuse_policy: str = "reference_only"
    media_policy: str = "do_not_download"
    safety_status: str = "OK"
    buzz_score: float | None = None
    buzz_rank: int | None = None
    is_top_post: bool = False
    why_it_grew: str | None = None
    replay_tip: str | None = None
    recommended_generation_mode: str | None = None
    mock: bool = False
    fetch_warn: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_item_id": self.raw_item_id,
            "source_id": self.source_id,
            "source_platform": self.source_platform,
            "source_handle": self.source_handle,
            "source_url": self.source_url,
            "target_account_id": self.target_account_id,
            "fetch_adapter": self.fetch_adapter,
            "fetch_method": self.fetch_method,
            "item_type": self.item_type,
            "post_id": self.post_id,
            "post_url": self.post_url,
            "author_handle": self.author_handle,
            "author_name": self.author_name,
            "text": self.text,
            "title": self.title,
            "description": self.description,
            "hashtags": self.hashtags,
            "mentions": self.mentions,
            "posted_at": self.posted_at,
            "like_count": self.like_count,
            "reply_count": self.reply_count,
            "repost_count": self.repost_count,
            "quote_count": self.quote_count,
            "bookmark_count": self.bookmark_count,
            "impression_count": self.impression_count,
            "view_count": self.view_count,
            "follower_count": self.follower_count,
            "image_urls": self.image_urls,
            "video_urls": self.video_urls,
            "thumbnail_url": self.thumbnail_url,
            "duration_seconds": self.duration_seconds,
            "transcript": self.transcript,
            "raw_payload_compact": self.raw_payload_compact,
            "fetched_at": self.fetched_at,
            "rights_status": self.rights_status,
            "reuse_policy": self.reuse_policy,
            "media_policy": self.media_policy,
            "safety_status": self.safety_status,
            "buzz_score": self.buzz_score,
            "buzz_rank": self.buzz_rank,
            "is_top_post": self.is_top_post,
            "why_it_grew": self.why_it_grew,
            "replay_tip": self.replay_tip,
            "recommended_generation_mode": self.recommended_generation_mode,
            "mock": self.mock,
            "fetch_warn": self.fetch_warn,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RawSourceItem":
        fields = {k for k in cls.__dataclass_fields__}
        kwargs = {k: v for k, v in d.items() if k in fields}
        return cls(**kwargs)


@dataclass
class FetchResult:
    """1回のfetch実行結果。"""
    adapter: str
    source_id: str
    status: str          # OK / BLOCKED / NOT_INSTALLED / NOT_READY / WARN / ERROR
    items: list[RawSourceItem] = field(default_factory=list)
    message: str = ""
    warn: str = ""
    mock: bool = False
    dry_run: bool = False
    fetched_at: str = field(default_factory=_now_jst)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "source_id": self.source_id,
            "status": self.status,
            "item_count": len(self.items),
            "items": [i.to_dict() for i in self.items],
            "message": self.message,
            "warn": self.warn,
            "mock": self.mock,
            "dry_run": self.dry_run,
            "fetched_at": self.fetched_at,
        }


class BaseFetcher:
    """Source Fetcher 抽象基底クラス。

    サブクラスは fetch() を実装する。
    - mock=True: モックデータを返す。ネットワーク接続なし。
    - confirm_fetch=False: 実取得をBLOCK。
    - confirm_download=False: ファイル保存をBLOCK。
    """

    adapter_name: str = "base"
    supported_platforms: list[str] = []

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
        raise NotImplementedError(f"{self.__class__.__name__}.fetch() が未実装です")

    def _blocked(self, source: dict, reason: str) -> FetchResult:
        return FetchResult(
            adapter=self.adapter_name,
            source_id=source.get("source_id", ""),
            status="BLOCKED",
            message=f"BLOCKED: {reason}",
        )

    def _not_installed(self, source: dict, tool: str) -> FetchResult:
        return FetchResult(
            adapter=self.adapter_name,
            source_id=source.get("source_id", ""),
            status="NOT_INSTALLED",
            message=f"NOT_INSTALLED: {tool} がインストールされていません。",
            warn=f"{tool} をインストールしてください。",
        )

    def _make_mock_item(
        self,
        source: dict,
        target_account_id: str,
        index: int = 0,
    ) -> RawSourceItem:
        platform = source.get("source_platform", "unknown")
        handle = source.get("source_handle", "@mock_handle")
        return RawSourceItem(
            source_id=source.get("source_id", "mock_source"),
            source_platform=platform,
            source_handle=handle,
            source_url=source.get("source_url", ""),
            target_account_id=target_account_id,
            fetch_adapter=self.adapter_name,
            fetch_method="mock",
            item_type="video" if platform in ("youtube", "tiktok", "youtube_shorts") else "post",
            post_id=f"mock_{platform}_{index:03d}",
            post_url=f"https://{platform}.com/mock/{index}",
            author_handle=handle,
            author_name=f"Mock Account {index}",
            text=f"【モック】{platform} 参考投稿 #{index+1} — 伸びているコンテンツ例",
            title=f"モック動画タイトル #{index+1}" if platform in ("youtube", "tiktok") else "",
            description=f"モック動画説明 #{index+1}",
            like_count=1000 * (index + 1),
            view_count=10000 * (index + 1),
            reply_count=50 * (index + 1),
            repost_count=100 * (index + 1),
            impression_count=50000 * (index + 1),
            thumbnail_url=f"https://mock.example.com/thumb/{index}.jpg",
            rights_status=source.get("rights_policy", "reference_only"),
            reuse_policy=source.get("reuse_policy", "reference_only"),
            media_policy=source.get("media_policy", "do_not_download"),
            mock=True,
        )
