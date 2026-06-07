"""
weekly_report_builder.py - 週次改善レポートビルダー（Phase 4.4）

posted_results / queue / learning_rules / suggestions から
アカウント別の週次レポートを構築する。

自動反映は行わない。Hermes分析用ファイルとして出力する。
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any


# 投稿タイプの定義
POST_TYPES = {
    "reference_based": "参照投稿ベース",
    "original_hypothesis": "オリジナル仮説",
    "video_clip_reference": "動画クリップ参照",
}


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(float(str(val)))
    except (TypeError, ValueError):
        return default


def _week_range(now: datetime) -> tuple[datetime, datetime]:
    """直近7日間の範囲を返す。"""
    end = now
    start = end - timedelta(days=7)
    return start, end


def _is_in_range(row: dict, start: datetime, end: datetime) -> bool:
    """posted_at が期間内か確認。"""
    posted_at_str = str(row.get("posted_at", ""))
    if not posted_at_str:
        return False
    try:
        dt = datetime.fromisoformat(posted_at_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return start <= dt <= end
    except ValueError:
        return False


def _get_impression_score(post: dict) -> float:
    """PV系指標スコアを計算（impressions / views）。"""
    impressions = _safe_float(post.get("impressions", 0))
    views = _safe_float(post.get("views", impressions))
    return max(impressions, views)


def _get_cv_score(post: dict) -> float:
    """CV系指標スコアを計算（engagement_rate / likes / follows）。"""
    eng = _safe_float(post.get("engagement_rate", 0))
    likes = _safe_float(post.get("likes", 0))
    follows = _safe_float(post.get("follow_count_delta", 0))
    return eng * 100 + likes + follows * 5


def build_weekly_report(
    account_id: str,
    *,
    posted_results: list[dict],
    queue_items: list[dict],
    learning_rules: list[dict],
    suggestions: list[dict],
    category_scores: list[dict],
    now: datetime | None = None,
) -> dict:
    """週次改善レポートを構築して辞書で返す。"""
    if now is None:
        now = datetime.now(timezone.utc)

    start, end = _week_range(now)

    # ---- 期間内投稿の抽出 ----
    recent_posts = [p for p in posted_results if _is_in_range(p, start, end)]
    all_posts = posted_results

    # ---- 投稿タイプ別集計 ----
    type_breakdown: dict[str, dict] = {}
    for ptype, label in POST_TYPES.items():
        type_posts = [
            p for p in recent_posts
            if str(p.get("generation_type", "")).lower() == ptype
        ]
        type_all = [
            p for p in all_posts
            if str(p.get("generation_type", "")).lower() == ptype
        ]
        type_breakdown[ptype] = {
            "label": label,
            "recent_count": len(type_posts),
            "total_count": len(type_all),
            "avg_impressions": (
                sum(_get_impression_score(p) for p in type_posts) / len(type_posts)
                if type_posts else 0.0
            ),
            "avg_cv_score": (
                sum(_get_cv_score(p) for p in type_posts) / len(type_posts)
                if type_posts else 0.0
            ),
        }

    # ---- プラットフォーム別集計 ----
    platform_breakdown: dict[str, int] = {}
    for p in recent_posts:
        platform = str(p.get("platform", "unknown"))
        platform_breakdown[platform] = platform_breakdown.get(platform, 0) + 1

    # ---- 伸びた投稿 / 伸びなかった投稿 ----
    sorted_by_pv = sorted(recent_posts, key=_get_impression_score, reverse=True)
    top_posts = sorted_by_pv[:3]
    low_posts = sorted_by_pv[-3:] if len(sorted_by_pv) > 3 else []

    # ---- 学習ルール集計 ----
    active_rules = [r for r in learning_rules if str(r.get("active", "")).lower() == "true"]
    waiting_suggestions = [
        s for s in suggestions
        if str(s.get("status", "")).upper() == "WAITING_REVIEW"
    ]

    # ---- 次週の改善仮説 ----
    hypotheses = _generate_hypotheses(
        account_id=account_id,
        recent_posts=recent_posts,
        waiting_suggestions=waiting_suggestions,
        top_posts=top_posts,
        low_posts=low_posts,
    )

    # ---- レポート構築 ----
    return {
        "report_type": "weekly_growth_report",
        "account_id": account_id,
        "generated_at": now.isoformat(),
        "period": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "label": "直近7日間",
        },
        "summary": {
            "recent_post_count": len(recent_posts),
            "total_post_count": len(all_posts),
            "platform_breakdown": platform_breakdown,
            "type_breakdown": type_breakdown,
        },
        "performance": {
            "pv_metrics": {
                "label": "PV系指標（impressions / views）",
                "top_posts": [_slim_post(p) for p in top_posts],
                "top_count": len(top_posts),
            },
            "cv_metrics": {
                "label": "CV系指標（engagement_rate / likes / follow_delta）",
                "low_posts": [_slim_post(p) for p in low_posts],
                "low_count": len(low_posts),
            },
        },
        "learning_status": {
            "active_rules_count": len(active_rules),
            "waiting_suggestions_count": len(waiting_suggestions),
        },
        "next_hypotheses": hypotheses,
        "meta": {
            "auto_apply": False,
            "note": "このレポートの内容を自動反映しない。承認フローを経ること。",
        },
    }


def _slim_post(post: dict) -> dict:
    """レポート用に投稿情報をスリム化（機密情報除去）。"""
    return {
        "post_id": post.get("post_id", post.get("draft_id", "?")),
        "platform": post.get("platform", "?"),
        "generation_type": post.get("generation_type", "?"),
        "posted_at": post.get("posted_at", "?"),
        "pv_score": _get_impression_score(post),
        "cv_score": round(_get_cv_score(post), 2),
    }


def _generate_hypotheses(
    account_id: str,
    recent_posts: list[dict],
    waiting_suggestions: list[dict],
    top_posts: list[dict],
    low_posts: list[dict],
) -> list[dict]:
    """次週の改善仮説を生成する（自動反映しない）。"""
    hypotheses: list[dict] = []

    if len(recent_posts) < 3:
        hypotheses.append({
            "type": "data_insufficient",
            "hypothesis": "投稿数が少ないため分析が不十分。来週も同じペースで投稿を続ける。",
            "auto_apply": False,
        })
        return hypotheses

    # PV高い投稿のパターン分析
    if top_posts:
        top_types = [p.get("generation_type", "unknown") for p in top_posts]
        most_common_type = max(set(top_types), key=top_types.count)
        hypotheses.append({
            "type": "type_focus",
            "hypothesis": f"高PV投稿の多いタイプは '{most_common_type}'。このタイプを増やすことで効果が期待できる。",
            "evidence_count": top_types.count(most_common_type),
            "auto_apply": False,
        })

    # PV低い投稿のパターン分析
    if low_posts:
        low_types = [p.get("generation_type", "unknown") for p in low_posts]
        hypotheses.append({
            "type": "underperform_review",
            "hypothesis": f"低パフォーマンス投稿のタイプ: {list(set(low_types))}。フックや訴求の見直しが必要。",
            "auto_apply": False,
        })

    # 待機中改善提案がある場合
    if waiting_suggestions:
        high_pri = [s for s in waiting_suggestions if str(s.get("priority", "")).lower() == "high"]
        if high_pri:
            hypotheses.append({
                "type": "suggestion_review",
                "hypothesis": f"優先度高の未承認提案が{len(high_pri)}件ある。review_improvement_suggestions.py でレビューを。",
                "suggestion_ids": [s.get("suggestion_id") for s in high_pri[:3]],
                "auto_apply": False,
            })

    return hypotheses


def build_markdown_report(report: dict) -> str:
    """レポート辞書を Markdown 形式に変換する。"""
    account_id = report["account_id"]
    generated_at = report.get("generated_at", "?")
    period = report.get("period", {})
    summary = report.get("summary", {})
    performance = report.get("performance", {})
    learning = report.get("learning_status", {})
    hypotheses = report.get("next_hypotheses", [])

    lines = [
        f"# 週次改善レポート: {account_id}",
        f"",
        f"**生成日時**: {generated_at}",
        f"**対象期間**: {period.get('start', '?')} 〜 {period.get('end', '?')}",
        f"",
        f"---",
        f"",
        f"## 投稿実績サマリー",
        f"",
        f"- 期間内投稿数: **{summary.get('recent_post_count', 0)}件**",
        f"- 全体投稿数: {summary.get('total_post_count', 0)}件",
        f"",
        f"### プラットフォーム別",
        f"",
    ]

    platform_breakdown = summary.get("platform_breakdown", {})
    for platform, count in platform_breakdown.items():
        lines.append(f"- {platform}: {count}件")
    if not platform_breakdown:
        lines.append("- (データなし)")
    lines.append("")

    lines += [
        f"### 投稿タイプ別",
        f"",
    ]
    type_breakdown = summary.get("type_breakdown", {})
    for ptype, info in type_breakdown.items():
        label = info.get("label", ptype)
        count = info.get("recent_count", 0)
        avg_pv = info.get("avg_impressions", 0)
        lines.append(f"- **{label}** (`{ptype}`): {count}件 (avg PV: {avg_pv:.1f})")
    lines.append("")

    lines += [
        f"## パフォーマンス分析",
        f"",
        f"### 伸びた投稿 (PV系 Top 3)",
        f"",
    ]
    top_posts = performance.get("pv_metrics", {}).get("top_posts", [])
    for p in top_posts:
        lines.append(f"- `{p.get('post_id', '?')}` ({p.get('platform', '?')}) - PV: {p.get('pv_score', 0):.0f}")
    if not top_posts:
        lines.append("- (データなし)")
    lines.append("")

    lines += [
        f"### 伸びなかった投稿",
        f"",
    ]
    low_posts = performance.get("cv_metrics", {}).get("low_posts", [])
    for p in low_posts:
        lines.append(f"- `{p.get('post_id', '?')}` ({p.get('platform', '?')}) - CV: {p.get('cv_score', 0):.2f}")
    if not low_posts:
        lines.append("- (データなし)")
    lines.append("")

    lines += [
        f"## 学習システム状態",
        f"",
        f"- 有効ルール (active=true): {learning.get('active_rules_count', 0)}件",
        f"- レビュー待ち提案: {learning.get('waiting_suggestions_count', 0)}件",
        f"",
        f"## 次週の改善仮説",
        f"",
        f"> **注意**: 以下は仮説です。自動反映しません。承認フロー経由で実施してください。",
        f"",
    ]
    for i, h in enumerate(hypotheses, 1):
        lines.append(f"{i}. [{h.get('type', '?')}] {h.get('hypothesis', '?')}")
    if not hypotheses:
        lines.append("(仮説なし)")
    lines.append("")

    lines += [
        f"---",
        f"",
        f"*このファイルは Hermes Agent 分析用です。git commit しないでください。*",
    ]
    return "\n".join(lines)
