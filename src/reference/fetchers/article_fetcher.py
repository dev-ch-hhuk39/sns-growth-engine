"""
article_fetcher.py - note / 記事 URL からメタデータを取得する Fetcher

安全ルール:
  - confirm_fetch=True が必要（デフォルト BLOCKED）
  - 実 HTTP リクエストは confirm_fetch=True の場合のみ
  - mock=True はネットワーク接続なし
  - cookie / 認証情報は出力しない
"""
from __future__ import annotations

import re
from typing import Any

from .base_fetcher import BaseFetcher, FetchResult, RawSourceItem, _now_jst, _new_id


class ArticleFetcher(BaseFetcher):
    """note.com / 記事 URL からタイトル・本文・メタデータを取得するアダプター。

    実装方針:
      - mock モード: 固定データを返す
      - 実 fetch: requests + BeautifulSoup で HTML を取得しパース
      - require_transform=true のソースは生テキストをそのまま使わずに変換必須
    """

    adapter_name = "article_fetcher"
    supported_platforms = ["note", "article"]

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
        platform = source.get("platform", "note")
        url = source.get("url", "")

        if mock:
            return self._mock_result(source_id, platform, url, target_account_id)

        if not confirm_fetch:
            return self._blocked(source, "confirm_fetch=True が必要です")

        if not source.get("allow_network_fetch", False):
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source.get("source_id", ""),
                status="NOT_READY",
                items=[],
                message="allow_network_fetch=false のためネットワーク取得不可",
            )

        return self._real_fetch(source, target_account_id, max_items)

    def _mock_result(
        self,
        source_id: str,
        platform: str,
        url: str,
        target_account_id: str,
    ) -> FetchResult:
        items = [
            RawSourceItem(
                raw_item_id=_new_id(),
                source_id=source_id,
                source_platform=platform,
                source_url=url,
                target_account_id=target_account_id,
                fetch_adapter=self.adapter_name,
                fetch_method="article_html_parse",
                item_type="article",
                post_url=url,
                title="[MOCK] サンプル記事タイトル",
                description="[MOCK] 記事の要約や導入文がここに入ります。",
                text="[MOCK] 記事本文テキスト。複数段落にわたる内容。",
                like_count=120,
                view_count=3000,
                posted_at="2026-06-01T09:00:00+09:00",
                rights_status="reference_only",
                reuse_policy="reference_only",
                media_policy="plan_only",
                mock=True,
            )
        ]
        return FetchResult(
            adapter=self.adapter_name,
            source_id=source_id,
            status="OK",
            items=items,
            mock=True,
            message="mock data",
        )

    def _real_fetch(
        self,
        source: dict[str, Any],
        target_account_id: str,
        max_items: int,
    ) -> FetchResult:
        """実 HTTP fetch（confirm_fetch=True の場合のみ到達）"""
        source_id = source.get("source_id", "")
        urls: list[str] = source.get("urls", [])
        if not urls and source.get("url"):
            urls = [source["url"]]

        items: list[RawSourceItem] = []
        for url in urls[:max_items]:
            item = self._fetch_single_article(url, source, target_account_id)
            if item:
                items.append(item)

        status = "OK" if items else "NO_ITEMS"
        return FetchResult(
            adapter=self.adapter_name,
            source_id=source_id,
            status=status,
            items=items,
            fetched_at=_now_jst(),
        )

    def _fetch_single_article(
        self,
        url: str,
        source: dict[str, Any],
        target_account_id: str,
    ) -> RawSourceItem | None:
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            return None

        try:
            resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        except Exception:
            return None

        soup = BeautifulSoup(resp.text, "html.parser")

        title = soup.find("title")
        title_text = title.get_text(strip=True) if title else ""

        og_desc = soup.find("meta", property="og:description")
        description = og_desc.get("content", "") if og_desc else ""

        body_el = soup.find("article") or soup.find("main") or soup.body
        body_text = body_el.get_text(separator="\n", strip=True) if body_el else ""
        body_text = re.sub(r"\n{3,}", "\n\n", body_text)[:4000]

        return RawSourceItem(
            raw_item_id=_new_id(),
            source_id=source.get("source_id", ""),
            source_platform=source.get("platform", "note"),
            source_url=url,
            target_account_id=target_account_id,
            fetch_adapter=self.adapter_name,
            fetch_method="article_html_parse",
            item_type="article",
            post_url=url,
            title=title_text,
            description=description,
            text=body_text,
            rights_status="reference_only",
            reuse_policy="reference_only",
            media_policy="plan_only",
            fetched_at=_now_jst(),
        )
