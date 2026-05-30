"""
x_reference_collector.py — X API からの参考投稿収集（Phase 2.10 で本実装）

移植元: X_autopost_yoru/x_collect_posts.py
Phase 2.8 ではスタブとして public API のみを定義する。
"""
from __future__ import annotations

from typing import Any


def collect_account_posts(
    account_name: str,
    bearer_token: str,
    max_results: int = 10,
    since_id: str | None = None,
) -> list[dict[str, Any]]:
    """監視アカウントの最新投稿を取得する（Phase 2.10 で実装）。"""
    raise NotImplementedError("Phase 2.10 で実装予定")


def collect_keyword_posts(
    keyword: str,
    bearer_token: str,
    max_results: int = 10,
    since_id: str | None = None,
) -> list[dict[str, Any]]:
    """キーワード検索で投稿を取得する（Phase 2.10 で実装）。"""
    raise NotImplementedError("Phase 2.10 で実装予定")


def normalize_post(raw: dict[str, Any], account_id: str, source_type: str) -> dict[str, Any]:
    """X API レスポンスを reference_posts スキーマに変換する（Phase 2.10 で実装）。"""
    raise NotImplementedError("Phase 2.10 で実装予定")
