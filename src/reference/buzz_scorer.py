"""
buzz_scorer.py - Buzz Scoring Engine（Phase 9）

raw_source_items に buzz_score / buzz_rank / is_top_post /
why_it_grew / replay_tip / recommended_generation_mode を付与する。

APIなし方針: 実APIを呼ばず、取得済みmetricsだけでスコアリング。
metricsが不足していても暫定スコアを出す。
"""
from __future__ import annotations

import math
from typing import Any

from .fetchers.base_fetcher import RawSourceItem


def score_items(
    items: list[RawSourceItem],
    source_platform: str = "",
    top_n: int = 5,
) -> list[RawSourceItem]:
    """items にbuzzスコアを付与してbuzz_rankでソートして返す。"""
    if not items:
        return items

    scored = [_score_one(item) for item in items]

    # sourceごとの相対評価 (同一source_id内でのランク)
    source_groups: dict[str, list[RawSourceItem]] = {}
    for item in scored:
        source_groups.setdefault(item.source_id, []).append(item)

    for grp_items in source_groups.values():
        grp_items.sort(key=lambda x: x.buzz_score or 0, reverse=True)
        for rank, item in enumerate(grp_items, 1):
            item.buzz_rank = rank
            item.is_top_post = rank <= top_n

    # 全体ソート
    scored.sort(key=lambda x: x.buzz_score or 0, reverse=True)
    return scored


def _score_one(item: RawSourceItem) -> RawSourceItem:
    """1件にbuzz_scoreを計算して付与する。"""
    s = _calc_buzz_score(item)
    item.buzz_score = round(s, 4)
    item.why_it_grew = _why_it_grew(item, s)
    item.replay_tip = _replay_tip(item)
    item.recommended_generation_mode = _recommend_mode(item)
    return item


def _calc_buzz_score(item: RawSourceItem) -> float:
    """buzz_score を 0.0〜1.0 で計算する。

    metricsが少ない場合は利用可能な指標だけで暫定スコアを出す。
    """
    like = item.like_count or 0
    view = item.view_count or item.impression_count or 0
    reply = item.reply_count or 0
    repost = item.repost_count or 0
    bookmark = item.bookmark_count or 0
    follower = item.follower_count or 1

    # engagement rate (foll based)
    er_foll = (like + reply * 2 + repost * 3 + bookmark * 2) / max(follower, 1)

    # view-based engagement rate
    er_view = (like + reply + repost) / max(view, 1) if view > 0 else 0.0

    # 絶対数スコア (対数スケール)
    abs_likes = _log_norm(like, ceiling=100_000)
    abs_views = _log_norm(view, ceiling=10_000_000)

    # 動画有無ボーナス
    media_bonus = 0.05 if item.image_urls else 0.0
    video_bonus = 0.10 if item.video_urls or item.item_type == "video" else 0.0

    # platform別重み
    platform = item.source_platform
    if platform in ("youtube", "tiktok", "youtube_shorts"):
        score = (
            abs_views * 0.35
            + _log_norm(like, ceiling=500_000) * 0.25
            + min(er_view * 10, 1.0) * 0.20
            + video_bonus * 0.10
            + media_bonus * 0.05
            + min(er_foll * 5, 1.0) * 0.05
        )
    else:
        # x / threads
        score = (
            abs_likes * 0.30
            + min(er_foll * 20, 1.0) * 0.25
            + _log_norm(repost, ceiling=10_000) * 0.20
            + _log_norm(bookmark, ceiling=5_000) * 0.10
            + media_bonus * 0.05
            + video_bonus * 0.05
            + min(er_view * 10, 1.0) * 0.05
        )

    return max(0.0, min(1.0, score))


def _log_norm(value: int, ceiling: int = 10_000) -> float:
    if value <= 0:
        return 0.0
    return min(math.log1p(value) / math.log1p(ceiling), 1.0)


def _why_it_grew(item: RawSourceItem, score: float) -> str | None:
    reasons: list[str] = []

    like = item.like_count or 0
    view = item.view_count or 0
    repost = item.repost_count or 0
    bookmark = item.bookmark_count or 0

    if like >= 1000:
        reasons.append(f"いいね{like:,}件の高反応")
    if view >= 10000:
        reasons.append(f"再生数{view:,}回の高拡散")
    if repost >= 200:
        reasons.append(f"リポスト{repost:,}件で広まった")
    if bookmark >= 100:
        reasons.append(f"ブックマーク{bookmark:,}件の保存価値あり")
    if item.image_urls:
        reasons.append("画像付きで目を引いた")
    if item.video_urls or item.item_type == "video":
        reasons.append("動画コンテンツで視聴継続")
    if score >= 0.8:
        reasons.append("複数指標でトップ水準")
    elif score >= 0.5:
        reasons.append("平均以上のパフォーマンス")

    return "、".join(reasons) if reasons else None


def _replay_tip(item: RawSourceItem) -> str | None:
    tips: list[str] = []
    platform = item.source_platform

    if item.video_urls or item.item_type in ("video", "youtube_shorts"):
        tips.append("動画形式で再現: 冒頭3秒で引きを作る")
    if item.image_urls:
        tips.append("画像を添付して視覚的インパクトを出す")
    if item.hashtags:
        tips.append(f"ハッシュタグ例: {' '.join(item.hashtags[:3])}")
    if item.like_count and item.like_count >= 500:
        tips.append("hook文を最初の一文に凝縮する")
    if platform in ("x",):
        tips.append("スレッド化して続きを読みたくさせる")
    if platform in ("threads",):
        tips.append("箇条書きか短文連投で最後まで読ませる")
    if platform in ("tiktok", "youtube_shorts"):
        tips.append("15-30秒のshorts形式で再現")

    return " / ".join(tips[:3]) if tips else None


def _recommend_mode(item: RawSourceItem) -> str:
    if item.item_type == "trend_insight":
        return "original_hypothesis"
    if item.video_urls or item.item_type in ("video", "youtube_shorts"):
        if item.transcript:
            return "video_clip_reference"
        return "video_reference_no_transcript"
    if item.image_urls:
        return "reference_based_image"
    return "reference_based_text"


def filter_top_items(
    items: list[RawSourceItem],
    min_buzz_score: float = 0.3,
    top_n: int | None = None,
) -> list[RawSourceItem]:
    """is_top_post=True かつ min_buzz_score 以上のアイテムを返す。"""
    filtered = [i for i in items if (i.buzz_score or 0) >= min_buzz_score]
    if top_n is not None:
        filtered = filtered[:top_n]
    return filtered


def items_to_dicts(items: list[RawSourceItem]) -> list[dict[str, Any]]:
    return [i.to_dict() for i in items]
