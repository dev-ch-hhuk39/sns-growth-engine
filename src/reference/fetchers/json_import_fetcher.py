"""
json_import_fetcher.py - JSON / CSV / URL 手動インポート Fetcher（Phase 9）

手動でエクスポートしたJSON/CSVをraw_source_itemsに変換する。
実ネットワーク接続なし。最も安全なfallbackアダプター。
"""
from __future__ import annotations

import csv
import json
import os
from typing import Any

from .base_fetcher import BaseFetcher, FetchResult, RawSourceItem, _now_jst


class JsonImportFetcher(BaseFetcher):
    """手動JSON/CSV/URLエクスポートをraw_source_itemsに変換する。"""

    adapter_name = "json_import"
    supported_platforms = ["x", "threads", "tiktok", "youtube", "youtube_shorts", "instagram_reels"]

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
        import_path: str = "",
    ) -> FetchResult:
        source_id = source.get("source_id", "")
        collection_method = source.get("collection_method", "manual_json")

        if collection_method == "scrape_disallowed":
            return self._blocked(source, "collection_method=scrape_disallowed")

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
                message=f"MOCK: {len(items)}件のモックデータを返します。",
                mock=True,
                dry_run=dry_run,
            )

        # 実インポート
        if not import_path:
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="NOT_READY",
                message="import_path が未指定です。--import-path でJSONまたはCSVファイルを指定してください。",
            )

        if not os.path.isfile(import_path):
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="NOT_READY",
                message=f"ファイルが見つかりません: {import_path}",
            )

        ext = os.path.splitext(import_path)[1].lower()
        try:
            if ext == ".json":
                items = self._load_json(import_path, source, target_account_id, max_items)
            elif ext == ".csv":
                items = self._load_csv(import_path, source, target_account_id, max_items)
            else:
                return FetchResult(
                    adapter=self.adapter_name,
                    source_id=source_id,
                    status="NOT_READY",
                    message=f"未対応の形式: {ext}。.json または .csv を使用してください。",
                )
        except Exception as e:
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="ERROR",
                message=f"インポートエラー: {e}",
            )

        return FetchResult(
            adapter=self.adapter_name,
            source_id=source_id,
            status="OK",
            items=items,
            message=f"{len(items)}件をインポートしました。",
            mock=False,
            dry_run=dry_run,
        )

    def _load_json(
        self,
        path: str,
        source: dict,
        target_account_id: str,
        max_items: int,
    ) -> list[RawSourceItem]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        records: list[dict] = []
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            for key in ("items", "posts", "data", "results"):
                if key in data and isinstance(data[key], list):
                    records = data[key]
                    break
            else:
                records = [data]

        items = []
        for i, rec in enumerate(records[:max_items]):
            item = self._normalize_record(rec, source, target_account_id, i)
            items.append(item)
        return items

    def _load_csv(
        self,
        path: str,
        source: dict,
        target_account_id: str,
        max_items: int,
    ) -> list[RawSourceItem]:
        items = []
        with open(path, encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i >= max_items:
                    break
                item = self._normalize_record(dict(row), source, target_account_id, i)
                items.append(item)
        return items

    def _normalize_record(
        self,
        rec: dict[str, Any],
        source: dict,
        target_account_id: str,
        index: int,
    ) -> RawSourceItem:
        platform = source.get("source_platform", rec.get("platform", "unknown"))

        def _int(v: Any) -> int:
            try:
                return int(float(str(v).replace(",", "")))
            except Exception:
                return 0

        def _str(v: Any) -> str:
            return str(v) if v is not None else ""

        hashtags = rec.get("hashtags", [])
        if isinstance(hashtags, str):
            hashtags = [h.strip() for h in hashtags.replace(",", " ").split() if h.startswith("#")]

        image_urls = rec.get("image_urls", rec.get("images", []))
        if isinstance(image_urls, str):
            image_urls = [u.strip() for u in image_urls.split(",") if u.strip()]

        video_urls = rec.get("video_urls", rec.get("videos", []))
        if isinstance(video_urls, str):
            video_urls = [u.strip() for u in video_urls.split(",") if u.strip()]

        return RawSourceItem(
            source_id=source.get("source_id", ""),
            source_platform=platform,
            source_handle=source.get("source_handle", _str(rec.get("author_handle", ""))),
            source_url=source.get("source_url", ""),
            target_account_id=target_account_id,
            fetch_adapter=self.adapter_name,
            fetch_method="json_import",
            item_type=_str(rec.get("item_type", "post")),
            post_id=_str(rec.get("post_id", rec.get("id", f"import_{index}"))),
            post_url=_str(rec.get("post_url", rec.get("url", ""))),
            author_handle=_str(rec.get("author_handle", rec.get("handle", ""))),
            author_name=_str(rec.get("author_name", rec.get("name", ""))),
            text=_str(rec.get("text", rec.get("body", rec.get("content", "")))),
            title=_str(rec.get("title", "")),
            description=_str(rec.get("description", "")),
            hashtags=hashtags if isinstance(hashtags, list) else [],
            mentions=rec.get("mentions", []) if isinstance(rec.get("mentions", []), list) else [],
            posted_at=_str(rec.get("posted_at", rec.get("created_at", rec.get("date", "")))),
            like_count=_int(rec.get("like_count", rec.get("likes", 0))),
            reply_count=_int(rec.get("reply_count", rec.get("replies", 0))),
            repost_count=_int(rec.get("repost_count", rec.get("retweets", rec.get("reposts", 0)))),
            quote_count=_int(rec.get("quote_count", rec.get("quotes", 0))),
            bookmark_count=_int(rec.get("bookmark_count", rec.get("bookmarks", 0))),
            impression_count=_int(rec.get("impression_count", rec.get("impressions", 0))),
            view_count=_int(rec.get("view_count", rec.get("views", rec.get("play_count", 0)))),
            follower_count=_int(rec.get("follower_count", rec.get("followers", 0))),
            image_urls=image_urls if isinstance(image_urls, list) else [],
            video_urls=video_urls if isinstance(video_urls, list) else [],
            thumbnail_url=_str(rec.get("thumbnail_url", rec.get("thumbnail", ""))),
            duration_seconds=float(rec["duration_seconds"]) if rec.get("duration_seconds") else None,
            transcript=_str(rec["transcript"]) if rec.get("transcript") else None,
            raw_payload_compact={
                k: v for k, v in rec.items()
                if k not in ("transcript",) and not str(k).endswith("_raw")
            },
            fetched_at=_now_jst(),
            rights_status=source.get("rights_policy", "reference_only"),
            reuse_policy=source.get("reuse_policy", "reference_only"),
            media_policy=source.get("media_policy", "do_not_download"),
        )
