"""
last30days_fetcher.py - Last30Days Skill based Trend Fetcher（Phase 9）

個別投稿の保存ではなく、トレンド調査・ネタ抽出・最近伸びているテーマ取得。
出力: trend_insights → raw_source_items / generation_jobs 候補。
"""
from __future__ import annotations

import json
import subprocess
from typing import Any

from .base_fetcher import BaseFetcher, FetchResult, RawSourceItem, _now_jst


def _check_last30days() -> bool:
    try:
        result = subprocess.run(
            ["last30days", "--help"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


class Last30DaysFetcher(BaseFetcher):
    """last30days-skill を使ってトレンド・ネタ抽出を行う。

    このアダプターは個別投稿ではなく trend_insights を返す。
    trend_insights は generation_jobs の候補として使える。
    """

    adapter_name = "last30days_skill"
    supported_platforms = ["x", "tiktok", "youtube", "threads", "instagram_reels"]

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
        query: str = "",
        platforms: list[str] | None = None,
    ) -> FetchResult:
        source_id = source.get("source_id", "")
        platform = source.get("source_platform", "x")

        if mock:
            items = self._mock_trend_items(source, target_account_id, query or platform)
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="OK",
                items=items,
                message=f"MOCK: last30days トレンド {len(items)}件のモックデータを返します。",
                mock=True,
                dry_run=dry_run,
            )

        if not confirm_fetch:
            return self._blocked(
                source,
                "--confirm-fetch が指定されていません。実取得をブロックします。",
            )

        if not _check_last30days():
            return self._not_installed(
                source,
                "last30days (last30days-skill インストールが必要です)",
            )

        if not query:
            query = source.get("source_handle", platform)

        try:
            trends = self._run_last30days(
                query=query,
                platforms=platforms or [platform],
                limit=max_items,
            )
        except Exception as e:
            return FetchResult(
                adapter=self.adapter_name,
                source_id=source_id,
                status="ERROR",
                message=f"last30days 実行エラー: {e}",
            )

        items = self._trends_to_raw_items(trends, source, target_account_id)
        return FetchResult(
            adapter=self.adapter_name,
            source_id=source_id,
            status="OK",
            items=items,
            message=f"last30days トレンド {len(items)}件取得。",
            mock=False,
            dry_run=dry_run,
        )

    def _run_last30days(
        self, query: str, platforms: list[str], limit: int
    ) -> list[dict]:
        cmd = [
            "last30days",
            "trends",
            "--query", query,
            "--platforms", ",".join(platforms),
            "--limit", str(limit),
            "--output", "json",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(result.stderr[:300])

        data = json.loads(result.stdout)
        if isinstance(data, list):
            return data
        return data.get("trends", data.get("items", []))

    def _trends_to_raw_items(
        self,
        trends: list[dict],
        source: dict,
        target_account_id: str,
    ) -> list[RawSourceItem]:
        items = []
        for i, t in enumerate(trends):
            text = t.get("topic", t.get("title", f"トレンド #{i+1}"))
            suggested_hooks = t.get("suggested_hooks", [])
            suggested_angles = t.get("suggested_angles", [])
            replay_tip = "; ".join(suggested_hooks[:2]) if suggested_hooks else None
            why = t.get("why_trending", t.get("reason", ""))

            item = RawSourceItem(
                source_id=source.get("source_id", ""),
                source_platform=source.get("source_platform", "x"),
                source_handle=source.get("source_handle", ""),
                source_url=source.get("source_url", ""),
                target_account_id=target_account_id,
                fetch_adapter=self.adapter_name,
                fetch_method="trend_insight",
                item_type="trend_insight",
                post_id=f"trend_{i:03d}",
                post_url="",
                text=text,
                title=text,
                description=t.get("description", ""),
                posted_at=_now_jst(),
                why_it_grew=why if why else None,
                replay_tip=replay_tip,
                recommended_generation_mode="original_hypothesis",
                raw_payload_compact={
                    "suggested_angles": suggested_angles,
                    "suggested_hooks": suggested_hooks,
                    "evidence_items": t.get("evidence_items", []),
                    "source_platforms": t.get("source_platforms", []),
                    "recommended_generation_jobs": t.get("recommended_generation_jobs", []),
                },
                fetched_at=_now_jst(),
                rights_status="reference_only",
                reuse_policy="reference_only",
                media_policy="do_not_download",
                mock=False,
            )
            items.append(item)
        return items

    def _mock_trend_items(
        self,
        source: dict,
        target_account_id: str,
        query: str,
    ) -> list[RawSourceItem]:
        mock_trends = [
            {
                "topic": f"【モック】トレンドトピック #{i+1} ({query})",
                "why_trending": f"短時間で{(i+1)*1000}件の反応を集めた",
                "suggested_hooks": [f"「{query}」で知ってた？", f"実は{query}でこれが伸びてる"],
                "suggested_angles": ["体験談", "TIPSまとめ", "意外な事実"],
                "description": f"過去30日で注目を集めているテーマ #{i+1}",
            }
            for i in range(3)
        ]
        return self._trends_to_raw_items(
            mock_trends,
            source,
            target_account_id,
        )
