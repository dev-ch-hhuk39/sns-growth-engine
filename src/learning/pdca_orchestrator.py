"""
pdca_orchestrator.py - PDCAオーケストレーター（Phase 7.E）

posted_results → 分析 → improvement_suggestions → 次回generation_jobs候補

禁止事項:
  - 実SNS投稿
  - learning_rules の auto active 化
  - prompt/code の自動書き換え
  - posted_results への本番投稿結果保存
  - queue.status を POSTED にする
  - beauty_account の実投稿・READY化
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

JST = timezone(timedelta(hours=9))


def _now_jst() -> str:
    return datetime.now(JST).strftime("%Y-%m-%dT%H:%M:%S+09:00")


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


def _filter_results(
    results: list[dict[str, Any]],
    account_id: str | None,
    platform: str | None,
    days: int | None,
) -> list[dict[str, Any]]:
    """posted_results をアカウント・プラットフォーム・期間でフィルタする。"""
    filtered = results
    if account_id:
        filtered = [r for r in filtered if r.get("account_id") == account_id]
    if platform:
        filtered = [r for r in filtered if r.get("platform") == platform]
    if days and days > 0:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        filtered = [r for r in filtered if str(r.get("posted_at", "")) >= cutoff]
    return filtered


def _compare_content_types(results: list[dict[str, Any]]) -> dict[str, Any]:
    """single_post / thread_series / reference_based / video_clip_reference を比較する。"""
    by_type: dict[str, list[dict]] = {}
    for r in results:
        ct = str(r.get("content_type") or r.get("generation_mode") or "unknown")
        by_type.setdefault(ct, []).append(r)

    summary: dict[str, Any] = {}
    for ct, items in by_type.items():
        likes = [int(i.get("likes") or 0) for i in items]
        views = [int(i.get("views") or i.get("impressions") or 0) for i in items]
        reposts = [int(i.get("reposts") or 0) for i in items]
        replies = [int(i.get("replies") or 0) for i in items]

        n = len(items)
        avg_likes = sum(likes) / n if n else 0
        avg_views = sum(views) / n if n else 0
        avg_er = (
            sum(
                (likes[i] + reposts[i] + replies[i]) / max(views[i], 1)
                for i in range(n)
            ) / n
            if n else 0
        )
        summary[ct] = {
            "count": n,
            "avg_likes": round(avg_likes, 2),
            "avg_views": round(avg_views, 2),
            "avg_engagement_rate": round(avg_er, 6),
        }
    return summary


def _generate_improvement_suggestions(
    analysis: dict[str, Any],
    account_id: str,
    platform: str,
    max_suggestions: int = 5,
) -> list[dict[str, Any]]:
    """分析結果から improvement_suggestions（WAITING_REVIEW）を生成する。"""
    suggestions: list[dict[str, Any]] = []
    content_comparison = analysis.get("content_type_comparison", {})

    best_type = ""
    best_er = -1.0
    for ct, stats in content_comparison.items():
        er = float(stats.get("avg_engagement_rate") or 0)
        if er > best_er:
            best_er = er
            best_type = ct

    if best_type:
        suggestions.append({
            "suggestion_id": f"sug_{_short_uuid()}",
            "account_id": account_id,
            "platform": platform,
            "type": "content_mix_ratio",
            "title": f"{best_type} の比率を増やす",
            "body": f"{best_type} のエンゲージメント率が最も高い（{best_er:.4f}）。content_mix の比率を見直すことを推奨。",
            "status": "WAITING_REVIEW",
            "active": False,
            "created_at": _now_jst(),
        })

    hook_analysis = analysis.get("hook_analysis", {})
    hook_er = float(hook_analysis.get("hook_metrics", {}).get("engagement_rate") or 0)
    non_hook_er = float(hook_analysis.get("non_hook_metrics", {}).get("engagement_rate") or 0)
    if hook_er > 0 and non_hook_er > 0:
        if hook_er < non_hook_er * 0.8:
            suggestions.append({
                "suggestion_id": f"sug_{_short_uuid()}",
                "account_id": account_id,
                "platform": platform,
                "type": "hook_improvement",
                "title": "hook 投稿のエンゲージメント率が低い",
                "body": f"hook のER={hook_er:.4f} が非hook={non_hook_er:.4f} より低い。hook 文面の改善を推奨。",
                "status": "WAITING_REVIEW",
                "active": False,
                "created_at": _now_jst(),
            })
        else:
            suggestions.append({
                "suggestion_id": f"sug_{_short_uuid()}",
                "account_id": account_id,
                "platform": platform,
                "type": "hook_strength",
                "title": "hook 投稿は効果的",
                "body": f"hook のER={hook_er:.4f} は良好。現在の hook スタイルを継続推奨。",
                "status": "WAITING_REVIEW",
                "active": False,
                "created_at": _now_jst(),
            })

    dropoff = analysis.get("dropoff", [])
    if len(dropoff) >= 3:
        first_impressions = int(dropoff[0].get("impressions") or 0)
        last_impressions = int(dropoff[-1].get("impressions") or 0)
        if first_impressions > 0:
            dropoff_rate = (first_impressions - last_impressions) / first_impressions
            if dropoff_rate > 0.7:
                suggestions.append({
                    "suggestion_id": f"sug_{_short_uuid()}",
                    "account_id": account_id,
                    "platform": platform,
                    "type": "thread_dropoff",
                    "title": f"thread_series のドロップオフが大きい（{dropoff_rate:.0%}）",
                    "body": "後半投稿への誘導を強化する（hook の引きつけ力向上 / 各投稿の冒頭改善）を推奨。",
                    "status": "WAITING_REVIEW",
                    "active": False,
                    "created_at": _now_jst(),
                })

    return suggestions[:max_suggestions]


def _generate_next_jobs(
    suggestions: list[dict[str, Any]],
    analysis: dict[str, Any],
    account_id: str,
    platform: str,
) -> list[dict[str, Any]]:
    """次回 generation_jobs 候補を PLANNED ステータスで生成する。"""
    jobs: list[dict[str, Any]] = []
    content_comparison = analysis.get("content_type_comparison", {})

    best_type = max(
        content_comparison.items(),
        key=lambda x: float(x[1].get("avg_engagement_rate") or 0),
        default=("single_post", {}),
    )[0] if content_comparison else "single_post"

    for i in range(3):
        jobs.append({
            "job_id": f"pj_{_short_uuid()}",
            "account_id": account_id,
            "platform": platform,
            "generation_mode": best_type,
            "status": "PLANNED",
            "source": "pdca_orchestrator",
            "created_at": _now_jst(),
        })
    return jobs


class PDCAOrchestrator:
    """PDCAオーケストレーター。

    posted_results → 分析 → improvement_suggestions → 次回jobs候補。
    全出力は WAITING_REVIEW / PLANNED 止まり。自動適用禁止。
    """

    def run(
        self,
        results: list[dict[str, Any]],
        account_id: str | None = None,
        platform: str | None = None,
        days: int | None = None,
        generate_next_plan: bool = False,
        max_suggestions: int = 5,
    ) -> dict[str, Any]:
        """PDCAサイクルを1回実行する。

        Args:
            results: posted_results 相当のリスト
            account_id: 絞り込みアカウントID
            platform: 絞り込みプラットフォーム
            days: 過去 N 日間に絞る
            generate_next_plan: True なら次回 jobs 候補も生成する
            max_suggestions: 最大提案件数

        Returns:
            分析結果・改善提案・次回jobs候補を含む辞書
        """
        filtered = _filter_results(results, account_id, platform, days)

        content_comparison = _compare_content_types(filtered)

        # hook / dropoff 分析（thread_series のみ）
        hook_analysis: dict[str, Any] = {}
        dropoff: list[dict] = []
        series_results = [r for r in filtered if r.get("series_id")]
        if series_results:
            try:
                from learning.post_result_analyzer import PostResultAnalyzer
                analyzer = PostResultAnalyzer()
                hook_analysis = analyzer.analyze_hook_effectiveness(
                    series_results, account_id=account_id
                )
                series_ids = list({r["series_id"] for r in series_results})
                if series_ids:
                    ts_analysis = analyzer.analyze_thread_series(
                        series_results, series_ids[0]
                    )
                    dropoff = ts_analysis.get("dropoff", [])
            except Exception:
                pass

        analysis = {
            "account_id": account_id,
            "platform": platform,
            "days": days,
            "total_results": len(filtered),
            "content_type_comparison": content_comparison,
            "hook_analysis": hook_analysis,
            "dropoff": dropoff,
        }

        suggestions = _generate_improvement_suggestions(
            analysis, account_id or "", platform or "", max_suggestions
        )

        next_jobs: list[dict] = []
        if generate_next_plan and filtered:
            next_jobs = _generate_next_jobs(
                suggestions, analysis, account_id or "", platform or ""
            )

        return {
            "pdca_run_id": f"pdca_{_short_uuid()}",
            "account_id": account_id,
            "platform": platform,
            "days": days,
            "analysis": analysis,
            "improvement_suggestions": suggestions,
            "suggestion_count": len(suggestions),
            "next_generation_jobs": next_jobs,
            "next_jobs_count": len(next_jobs),
            "safety_notes": [
                "improvement_suggestions は全て WAITING_REVIEW（自動適用禁止）",
                "learning_rules.active は false のまま",
                "next_generation_jobs は PLANNED（自動実行禁止）",
            ],
            "created_at": _now_jst(),
        }
