"""
article_reference_normalizer.py - 記事 RawSourceItem を reference_post 形式に変換
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

_JST = timezone(timedelta(hours=9))


def normalize_article_to_reference(
    raw: dict[str, Any],
    account_id: str = "",
    platform: str = "note",
) -> dict[str, Any]:
    """RawSourceItem (article) を reference_post 形式に正規化する。

    require_transform=True のソースは、生テキストをそのまま使わず
    必ずこの関数を通すこと。
    """
    now = datetime.now(_JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")

    title = raw.get("title", "")
    description = raw.get("description", "")
    text = raw.get("body", "") or raw.get("text", "")

    abstract = description or (text[:200] + "..." if len(text) > 200 else text) or title

    source_id = raw.get("source_id", "")
    post_id_suffix = f"{source_id[:12]}" if source_id else str(uuid.uuid4())[:8]

    return {
        "reference_post_id": f"ref_art_{post_id_suffix}",
        "source_id": raw.get("source_id", ""),
        "source_platform": platform,
        "source_url": raw.get("source_url", ""),
        "target_account_id": account_id,
        "item_type": "article",
        "title": title,
        "abstract": abstract,
        "full_text_available": bool(text),
        "like_count": raw.get("like_count", 0),
        "view_count": raw.get("view_count", 0),
        "posted_at": raw.get("posted_at", ""),
        "normalized_at": now,
        "rights_status": raw.get("rights_status", "reference_only"),
        "reuse_policy": raw.get("reuse_policy", "reference_only"),
        "require_transform": True,
        "adapter": raw.get("fetch_adapter", "article_fetcher"),
        "mock": raw.get("mock", False),
    }


def normalize_articles(
    raw_items: list[dict[str, Any]],
    account_id: str = "",
    platform: str = "note",
) -> list[dict[str, Any]]:
    """RawSourceItem リストをまとめて正規化する。"""
    return [
        normalize_article_to_reference(r, account_id=account_id, platform=platform)
        for r in raw_items
        if r.get("item_type") == "article" or r.get("fetch_adapter") == "article_fetcher"
    ]
