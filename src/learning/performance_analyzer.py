"""
performance_analyzer.py - パフォーマンス分析モジュール（Phase 4.0）

posted_results / queue / video_clip_candidates を分析して改善提案の根拠となる
メトリクスを算出する。Sheets 接続不要（export_learning_context.py 経由で利用）。

禁止事項:
  - 実Sheets書き込み（読み取り専用）
  - SNS本番投稿
  - 機密情報の出力
"""
from __future__ import annotations

from typing import Any


class PerformanceAnalyzer:
    """PerformanceAnalyzer - パフォーマンスメトリクス算出。

    外部からデータを渡す形式（Sheetsに直接接続しない）。
    """

    def analyze(
        self,
        *,
        account_id: str,
        posted_results: list[dict[str, Any]],
        queue_items: list[dict[str, Any]],
        video_clip_candidates: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """パフォーマンスメトリクスを算出する。

        Returns:
            {
                "account_id": str,
                "posted_count": int,
                "avg_likes": float,
                "avg_views": float,
                "avg_engagement_rate": float,
                "queue_ready_count": int,
                "queue_waiting_review_count": int,
                "video_clip_count": int,
                "text_policy_fail_rate": float,
                "rights_review_required_rate": float,
                "generation_mode_breakdown": dict,
            }
        """
        clips = video_clip_candidates or []

        posted_count = len(posted_results)
        avg_likes = _safe_avg(posted_results, "likes")
        avg_views = _safe_avg(posted_results, "views")
        avg_comments = _safe_avg(posted_results, "comments")
        avg_engagement_rate = (
            (avg_likes + avg_comments) / avg_views if avg_views > 0 else 0.0
        )

        ready = [q for q in queue_items if str(q.get("status", "")).upper() == "READY"]
        waiting = [q for q in queue_items if str(q.get("status", "")).upper() == "WAITING_REVIEW"]

        # text_policy_fail_rate
        text_fail = sum(
            1 for q in queue_items
            if str(q.get("text_policy_status", "")).upper() == "FAIL"
        )
        text_policy_fail_rate = text_fail / len(queue_items) if queue_items else 0.0

        # rights_review_required_rate
        rights_required = sum(
            1 for q in queue_items
            if str(q.get("rights_review_required", "false")).lower() == "true"
        )
        rights_review_required_rate = rights_required / len(queue_items) if queue_items else 0.0

        # generation_mode breakdown
        mode_counts: dict[str, int] = {}
        for q in queue_items:
            mode = str(q.get("generation_mode", "unknown")).strip() or "unknown"
            mode_counts[mode] = mode_counts.get(mode, 0) + 1

        return {
            "account_id": account_id,
            "posted_count": posted_count,
            "avg_likes": round(avg_likes, 2),
            "avg_views": round(avg_views, 2),
            "avg_engagement_rate": round(avg_engagement_rate, 4),
            "queue_ready_count": len(ready),
            "queue_waiting_review_count": len(waiting),
            "video_clip_count": len(clips),
            "text_policy_fail_rate": round(text_policy_fail_rate, 4),
            "rights_review_required_rate": round(rights_review_required_rate, 4),
            "generation_mode_breakdown": mode_counts,
        }


def _safe_avg(rows: list[dict[str, Any]], key: str) -> float:
    vals = []
    for r in rows:
        try:
            v = float(r.get(key, 0) or 0)
            vals.append(v)
        except (TypeError, ValueError):
            pass
    return sum(vals) / len(vals) if vals else 0.0
