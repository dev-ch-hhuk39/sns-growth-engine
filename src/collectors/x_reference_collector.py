"""
x_reference_collector.py — X API からの参考投稿収集

移植元: X_autopost_yoru/x_collect_posts.py
Phase 2.10 にて正規化ロジックを本実装。X API クライアントはスタブ（--use-x-api フラグで有効化）。

対応入力フォーマット:
  - X API v2 風 JSON（tweet オブジェクト）
  - fixture / AgentReach等の外部コレクター JSON
  - 既存 x_collect_posts.py が生成する JSON
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any


# ------------------------------------------------------------------ #
# 正規化ロジック
# ------------------------------------------------------------------ #

def normalize_post(
    raw: dict[str, Any],
    account_id: str,
    platform: str = "x",
) -> dict[str, Any]:
    """X API / fixture JSON を reference_posts スキーマへ変換する。

    入力キーは複数形式に対応:
      post_id       / id / tweet_id
      post_url      / url / tweet_url
      account_handle / user / author_handle
      account_name  / author_name / name
      posted_at     / created_at / timestamp
      text          / full_text / body
      like_count    / likes / public_metrics.like_count
      reply_count   / replies / public_metrics.reply_count
      repost_count  / retweet_count / reposts / public_metrics.retweet_count
      bookmark_count / bookmarks / public_metrics.bookmark_count
      impression_count / views / public_metrics.impression_count
      image_urls    / media_urls (image only)
      video_urls    / media_urls (video only)
      matched_keywords / keywords
      source_type
      hook_text     / extracted_hook
    """
    # --- post_id ---
    post_id = str(
        raw.get("post_id")
        or raw.get("id")
        or raw.get("tweet_id")
        or ""
    )

    # --- post_url ---
    post_url = str(
        raw.get("post_url")
        or raw.get("url")
        or raw.get("tweet_url")
        or ""
    )
    if not post_url and post_id:
        handle = raw.get("account_handle") or raw.get("user") or ""
        if handle:
            post_url = f"https://x.com/{handle}/status/{post_id}"

    # --- author / account_handle ---
    account_handle = str(
        raw.get("account_handle")
        or raw.get("user")
        or raw.get("author_handle")
        or ""
    )
    author = str(
        raw.get("account_name")
        or raw.get("author_name")
        or raw.get("name")
        or account_handle
    )

    # --- published_at ---
    published_at = str(
        raw.get("posted_at")
        or raw.get("created_at")
        or raw.get("timestamp")
        or ""
    )

    # --- text ---
    original_text = str(
        raw.get("text")
        or raw.get("full_text")
        or raw.get("body")
        or ""
    )

    # --- public_metrics ネスト対応 ---
    metrics: dict[str, Any] = raw.get("public_metrics", {}) or {}

    def _metric(key: str, alt_key: str, alt_key2: str = "") -> int:
        v = raw.get(key) or raw.get(alt_key) or (raw.get(alt_key2) if alt_key2 else None) or metrics.get(key) or 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    likes = _metric("like_count", "likes")
    reply_count = _metric("reply_count", "replies")
    repost_count = _metric("repost_count", "retweet_count", "reposts")
    bookmark_count = _metric("bookmark_count", "bookmarks")
    impressions = _metric("impression_count", "views")

    # --- media_urls ---
    image_urls: list[str] = raw.get("image_urls") or []
    video_urls: list[str] = raw.get("video_urls") or []

    # media_urls が混在している場合は image/video に分類済みとして扱う
    all_media = list(image_urls) + list(video_urls)
    media_urls_str = "|".join(m for m in all_media if m)

    # --- source_type ---
    source_type = str(
        raw.get("source_type")
        or ("keyword_search" if raw.get("matched_keywords") else "account_monitor")
    )

    # --- keywords ---
    kw_raw = raw.get("matched_keywords") or raw.get("keywords") or []
    if isinstance(kw_raw, list):
        keywords = "|".join(str(k) for k in kw_raw if k)
    else:
        keywords = str(kw_raw)

    # --- extracted_hook ---
    extracted_hook = str(
        raw.get("hook_text")
        or raw.get("extracted_hook")
        or _extract_first_line(original_text)
    )

    # --- collected_at ---
    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- imitation_risk デフォルト ---
    imitation_risk = str(raw.get("imitation_risk") or "unknown")

    return {
        "id": str(uuid.uuid4()),
        "created_at": collected_at,
        "account_id": account_id,
        "platform": platform,
        "post_url": post_url,
        "post_id": post_id,
        "title": "",
        "text": original_text,
        "media_urls": media_urls_str,
        "likes": likes,
        "reposts": repost_count,
        "impressions": impressions,
        "source_type": source_type,
        "author": author,
        "published_at": published_at,
        "hook_type": "",
        "extracted_hook": extracted_hook,
        "extracted_pain": "",
        "extracted_desire": "",
        "reusable_pattern": "",
        "imitation_risk": imitation_risk,
        "status": "new",
        "notes": "",
        # Phase 2.10 追加列
        "original_text": original_text,
        "account_handle": account_handle,
        "reply_count": reply_count,
        "bookmark_count": bookmark_count,
        "collected_at": collected_at,
        "keywords": keywords,
    }


def normalize_posts(
    raw_list: list[dict[str, Any]],
    account_id: str,
    platform: str = "x",
) -> list[dict[str, Any]]:
    """複数の raw 投稿を normalize_post でまとめて変換する。"""
    results = []
    for raw in raw_list:
        try:
            results.append(normalize_post(raw, account_id, platform))
        except Exception as e:
            print(f"[WARN] normalize_post スキップ (post_id={raw.get('post_id', '?')}): {e}")
    return results


def load_json_input(path: str) -> list[dict[str, Any]]:
    """JSONファイルを読み込んでdictのリストを返す。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # {"posts": [...]} 形式にも対応
        for key in ("posts", "data", "items", "results"):
            if isinstance(data.get(key), list):
                return data[key]
        return [data]
    raise ValueError(f"サポートされていないJSON形式: {type(data)}")


def classify_media(raw: dict[str, Any]) -> dict[str, bool]:
    """画像・動画・メディアの有無を判定する。"""
    image_urls = raw.get("image_urls") or []
    video_urls = raw.get("video_urls") or []
    has_image = len(image_urls) > 0
    has_video = len(video_urls) > 0
    return {
        "has_image": has_image,
        "has_video": has_video,
        "has_media": has_image or has_video,
    }


def make_dedup_key(post: dict[str, Any]) -> str:
    """重複判定キーを作る（post_id が最優先、なければ post_url）。"""
    if post.get("post_id"):
        return f"post_id:{post['post_id']}"
    if post.get("post_url"):
        return f"post_url:{post['post_url']}"
    return f"id:{post.get('id', '')}"


# ------------------------------------------------------------------ #
# X API クライアント（スタブ — Phase 2.10 で本実装）
# ------------------------------------------------------------------ #

def bearer_token_from_env() -> str:
    """環境変数 X_BEARER_TOKEN を返す。未設定なら ValueError。"""
    token = os.environ.get("X_BEARER_TOKEN", "").strip()
    if not token:
        raise ValueError("X_BEARER_TOKEN が設定されていません。.env を確認してください。")
    return token


def fetch_account_posts(
    account_handle: str,
    bearer_token: str,
    max_results: int = 10,
    since_id: str | None = None,
) -> list[dict[str, Any]]:
    """監視アカウントの最新投稿を X API v2 で取得する（Phase 2.10 で本実装）。

    今回は --use-x-api フラグなしでは呼ばないこと。
    """
    raise NotImplementedError(
        "X API 本番収集は Phase 2.10 で実装予定。--use-x-api フラグで明示的に有効化してください。"
    )


def fetch_keyword_posts(
    keyword: str,
    bearer_token: str,
    max_results: int = 10,
    since_id: str | None = None,
) -> list[dict[str, Any]]:
    """キーワード検索で投稿を X API v2 で取得する（Phase 2.10 で本実装）。"""
    raise NotImplementedError(
        "X API 本番収集は Phase 2.10 で実装予定。--use-x-api フラグで明示的に有効化してください。"
    )


# ------------------------------------------------------------------ #
# 内部ユーティリティ
# ------------------------------------------------------------------ #

def _extract_first_line(text: str) -> str:
    """テキストの最初の非空行を返す。hook_text の代替として使う。"""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""
