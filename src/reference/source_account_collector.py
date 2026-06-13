"""
source_account_collector.py - ソースアカウント投稿収集（Phase 7.B）

指定アカウントの投稿（手動JSON/CSV入力）をreference_posts形式に変換し、
バズ判定・伸びている投稿の選別を行う。

禁止事項:
  - 実X API / 実Threads API 呼び出し
  - Scraping
  - 規約違反となる取得
  - SNS本番投稿
"""
from __future__ import annotations

import csv
import io
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any


SUPPORTED_PLATFORMS = ["x", "threads", "tiktok", "youtube_shorts"]

METRIC_FIELDS = ["likes", "reposts", "replies", "views", "bookmarks"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


def compute_engagement_rate(post: dict[str, Any]) -> float:
    """エンゲージメント率を計算する（views > 0 の場合のみ）。"""
    views = float(post.get("views") or post.get("impression_count") or 0)
    if views <= 0:
        return 0.0
    likes = float(post.get("likes") or post.get("like_count") or 0)
    reposts = float(post.get("reposts") or post.get("repost_count") or 0)
    replies = float(post.get("replies") or post.get("reply_count") or 0)
    return (likes + reposts + replies) / views


def is_buzz_post(
    post: dict[str, Any],
    min_engagement_rate: float = 0.02,
    avg_likes: float = 0.0,
    avg_views: float = 0.0,
) -> bool:
    """バズ判定: エンゲージメント率 or アカウント平均比でバズとみなす。"""
    er = compute_engagement_rate(post)
    if er >= min_engagement_rate:
        return True
    likes = float(post.get("likes") or 0)
    if avg_likes > 0 and likes >= avg_likes * 2.0:
        return True
    views = float(post.get("views") or 0)
    if avg_views > 0 and views >= avg_views * 2.0:
        return True
    return False


def normalize_source_post(
    raw: dict[str, Any],
    account_id: str,
    source_platform: str,
    source_handle: str,
    reuse_policy: str = "reference_only",
) -> dict[str, Any]:
    """外部投稿JSONをreference_posts形式に正規化する。"""
    post_id = str(
        raw.get("post_id") or raw.get("id") or raw.get("tweet_id") or _short_uuid()
    )
    post_text = str(
        raw.get("text") or raw.get("full_text") or raw.get("body") or ""
    )
    media_urls = raw.get("media_urls") or raw.get("image_urls") or []
    if isinstance(media_urls, str):
        media_urls = [u for u in media_urls.split("|") if u]

    likes = int(raw.get("likes") or raw.get("like_count") or 0)
    reposts = int(raw.get("reposts") or raw.get("repost_count") or raw.get("retweet_count") or 0)
    replies = int(raw.get("replies") or raw.get("reply_count") or 0)
    views = int(raw.get("views") or raw.get("impression_count") or 0)
    bookmarks = int(raw.get("bookmarks") or raw.get("bookmark_count") or 0)

    source_url = str(
        raw.get("source_url") or raw.get("url") or raw.get("post_url") or ""
    )
    collected_at = raw.get("collected_at") or _now()
    content_type = str(raw.get("content_type") or "text")
    rights_status = str(raw.get("rights_status") or "unknown")

    er = compute_engagement_rate({
        "likes": likes, "reposts": reposts, "replies": replies, "views": views
    })

    return {
        "reference_post_id": f"src_{source_platform}_{post_id}",
        "account_id": account_id,
        "source_platform": source_platform,
        "source_account": source_handle,
        "source_url": source_url,
        "post_text": post_text,
        "media_urls": "|".join(media_urls) if media_urls else "",
        "likes": likes,
        "reposts": reposts,
        "replies": replies,
        "views": views,
        "bookmarks": bookmarks,
        "engagement_rate": round(er, 6),
        "collected_at": collected_at,
        "content_type": content_type,
        "rights_status": rights_status,
        "reuse_policy": reuse_policy,
        "status": "WAITING_REVIEW" if rights_status == "unknown" else "OK",
        "buzz": False,
    }


def compute_account_averages(posts: list[dict[str, Any]]) -> dict[str, float]:
    """投稿リストのアカウント平均メトリクスを計算する。"""
    if not posts:
        return {"avg_likes": 0.0, "avg_views": 0.0, "avg_er": 0.0}
    avg_likes = sum(float(p.get("likes") or 0) for p in posts) / len(posts)
    avg_views = sum(float(p.get("views") or 0) for p in posts) / len(posts)
    avg_er = sum(float(p.get("engagement_rate") or 0) for p in posts) / len(posts)
    return {"avg_likes": avg_likes, "avg_views": avg_views, "avg_er": avg_er}


def select_top_posts(
    posts: list[dict[str, Any]],
    top_n: int = 10,
    min_engagement_rate: float = 0.0,
) -> list[dict[str, Any]]:
    """エンゲージメント率が高い順に top_n 件を返す。"""
    filtered = [p for p in posts if p.get("engagement_rate", 0) >= min_engagement_rate]
    filtered.sort(key=lambda p: float(p.get("engagement_rate") or 0), reverse=True)
    return filtered[:top_n]


def collect_from_json(
    data: list[dict] | dict,
    account_id: str,
    source_platform: str,
    source_handle: str,
    min_engagement_rate: float = 0.0,
    top_n: int = 20,
    reuse_policy: str = "reference_only",
) -> dict[str, Any]:
    """JSON入力からreference_postsを生成して返す。"""
    raw_list: list[dict] = []
    if isinstance(data, dict):
        raw_list = data.get("posts", []) or data.get("items", []) or []
    elif isinstance(data, list):
        raw_list = data
    else:
        raw_list = []

    normalized = [
        normalize_source_post(r, account_id, source_platform, source_handle, reuse_policy)
        for r in raw_list
    ]

    avgs = compute_account_averages(normalized)
    for p in normalized:
        p["buzz"] = is_buzz_post(
            p,
            min_engagement_rate=min_engagement_rate,
            avg_likes=avgs["avg_likes"],
            avg_views=avgs["avg_views"],
        )

    top = select_top_posts(normalized, top_n=top_n, min_engagement_rate=min_engagement_rate)

    return {
        "account_id": account_id,
        "source_platform": source_platform,
        "source_handle": source_handle,
        "total_collected": len(normalized),
        "selected_count": len(top),
        "account_averages": avgs,
        "reference_posts": top,
        "collected_at": _now(),
    }


def collect_from_csv(
    csv_text: str,
    account_id: str,
    source_platform: str,
    source_handle: str,
    min_engagement_rate: float = 0.0,
    top_n: int = 20,
    reuse_policy: str = "reference_only",
) -> dict[str, Any]:
    """CSV文字列からreference_postsを生成して返す。"""
    reader = csv.DictReader(io.StringIO(csv_text))
    raw_list = [dict(row) for row in reader]
    return collect_from_json(
        raw_list,
        account_id=account_id,
        source_platform=source_platform,
        source_handle=source_handle,
        min_engagement_rate=min_engagement_rate,
        top_n=top_n,
        reuse_policy=reuse_policy,
    )
