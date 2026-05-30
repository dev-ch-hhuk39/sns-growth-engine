"""
reference_post_analyzer.py — 参考投稿のパフォーマンス分析（Phase 2.11 で本実装）

移植元: X_autopost_yoru/x_analyze_posts.py
Phase 2.8 ではスタブとして public API のみを定義する。

スコア計算式: performance_score = like + repost×3 + reply×2 + bookmark×4 + impression/100
"""
from __future__ import annotations

from typing import Any


def compute_performance_score(
    likes: int,
    reposts: int,
    replies: int,
    bookmarks: int,
    impressions: int,
) -> float:
    """パフォーマンススコアを計算する（Phase 2.11 で本実装）。"""
    raise NotImplementedError("Phase 2.11 で実装予定")


def detect_content_angle(text: str) -> str:
    """投稿テキストから切り口を分類する（Phase 2.11 で本実装）。

    分類: 体験談 / ノウハウ / 暴露 / 共感 / 質問 / その他
    """
    raise NotImplementedError("Phase 2.11 で実装予定")


def detect_hook_style(text: str) -> str:
    """書き出し型を分類する（Phase 2.11 で本実装）。

    分類: リスト型 / 質問型 / 暴露型 / 体験談型 / 断定型
    """
    raise NotImplementedError("Phase 2.11 で実装予定")


def analyze_post(
    post: dict[str, Any],
    account_percentile: float | None = None,
    keyword_percentile: float | None = None,
) -> dict[str, Any]:
    """1件の参考投稿を分析してスコア行を返す（Phase 2.11 で本実装）。"""
    raise NotImplementedError("Phase 2.11 で実装予定")
