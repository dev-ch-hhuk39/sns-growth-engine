"""
post_result_analyzer.py - 投稿結果分析（Phase 5.4）

posted_results タブのデータを分析し、パフォーマンス指標を返す。
外部API呼び出しなし。SNS投稿なし。

禁止事項:
  - 外部API呼び出し
  - SNS投稿
  - learning_rules.active=true の自動設定
  - prompt/code の自動書き換え
  - posted_results への本番投稿結果の保存
"""
from __future__ import annotations

from typing import Any


METRIC_FIELDS = [
    "impressions", "likes", "reposts", "replies",
    "profile_clicks", "line_clicks", "url_clicks",
]


class PostResultAnalyzer:
    """投稿結果を分析してメトリクスを返す。

    全処理はインメモリ。Sheets / API への書き込みは行わない。
    """

    # 改善提案を生成するエンゲージメント率の閾値
    LOW_ENGAGEMENT_THRESHOLD = 0.02   # 2% 未満
    MIN_RESULTS_FOR_ANALYSIS = 1      # 最低1件から分析

    def analyze(
        self,
        results: list[dict[str, Any]],
        *,
        account_id: str | None = None,
        platform: str | None = None,
    ) -> dict[str, Any]:
        """投稿結果リストを分析してメトリクスを返す。

        Args:
            results: posted_results 相当のリスト
            account_id: 絞り込み用アカウントID（Noneで全件）
            platform: 絞り込み用プラットフォーム（Noneで全件）

        Returns:
            分析結果辞書（account_id, platform, posted_count, metrics, top_posts,
            bottom_posts, by_generation_mode）
        """
        filtered = self._filter(results, account_id=account_id, platform=platform)

        if not filtered:
            return {
                "account_id": account_id,
                "platform": platform,
                "posted_count": 0,
                "metrics": {},
                "top_posts": [],
                "bottom_posts": [],
                "by_generation_mode": {},
                "pv_metrics": {},
                "cv_metrics": {},
            }

        metrics = self._aggregate_metrics(filtered)
        top, bottom = self._rank_posts(filtered)
        by_mode = self._by_generation_mode(filtered)
        pv_metrics, cv_metrics = self._split_pv_cv(metrics)

        return {
            "account_id": account_id,
            "platform": platform,
            "posted_count": len(filtered),
            "metrics": metrics,
            "top_posts": top[:5],
            "bottom_posts": bottom[:5],
            "by_generation_mode": by_mode,
            "pv_metrics": pv_metrics,
            "cv_metrics": cv_metrics,
        }

    def _filter(
        self,
        results: list[dict[str, Any]],
        account_id: str | None,
        platform: str | None,
    ) -> list[dict[str, Any]]:
        out = []
        for r in results:
            if account_id and str(r.get("account_id", "")) != account_id:
                continue
            if platform and str(r.get("platform", "")).lower() != platform.lower():
                continue
            out.append(r)
        return out

    def _safe_int(self, val: Any) -> int:
        try:
            return int(val)
        except (TypeError, ValueError):
            return 0

    def _aggregate_metrics(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        totals: dict[str, int] = {f: 0 for f in METRIC_FIELDS}
        for r in results:
            for f in METRIC_FIELDS:
                totals[f] += self._safe_int(r.get(f, 0))

        count = len(results)
        avg: dict[str, float] = {
            f: round(totals[f] / count, 2) for f in METRIC_FIELDS
        }

        total_impressions = totals.get("impressions", 0)
        total_likes = totals.get("likes", 0)
        eng_rate = round(total_likes / total_impressions, 4) if total_impressions > 0 else 0.0

        return {
            "total": totals,
            "average": avg,
            "engagement_rate": eng_rate,
            "count": count,
        }

    def _engagement_score(self, r: dict[str, Any]) -> float:
        impressions = self._safe_int(r.get("impressions", 0))
        likes = self._safe_int(r.get("likes", 0))
        if impressions == 0:
            return 0.0
        return likes / impressions

    def _rank_posts(
        self, results: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        scored = sorted(results, key=self._engagement_score, reverse=True)
        return scored, list(reversed(scored))

    def _by_generation_mode(
        self, results: list[dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        by_mode: dict[str, list[dict[str, Any]]] = {}
        for r in results:
            mode = str(r.get("generation_mode", "unknown"))
            by_mode.setdefault(mode, []).append(r)

        return {
            mode: self._aggregate_metrics(items)
            for mode, items in by_mode.items()
        }

    def _split_pv_cv(
        self, metrics: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        total = metrics.get("total", {})
        avg = metrics.get("average", {})

        pv_keys = ["impressions", "reposts"]
        cv_keys = ["likes", "replies", "profile_clicks", "line_clicks", "url_clicks"]

        pv_metrics = {
            "total": {k: total.get(k, 0) for k in pv_keys},
            "average": {k: avg.get(k, 0.0) for k in pv_keys},
        }
        cv_metrics = {
            "total": {k: total.get(k, 0) for k in cv_keys},
            "average": {k: avg.get(k, 0.0) for k in cv_keys},
        }
        return pv_metrics, cv_metrics

    def detect_forbidden_conflict(
        self,
        text: str,
        forbidden_keywords: list[str],
        forbidden_themes: list[str],
    ) -> tuple[bool, str]:
        """テキストが forbidden と矛盾するか確認。"""
        for kw in forbidden_keywords:
            if kw and kw in text:
                return True, f"forbidden_keyword: {kw!r}"
        for theme in forbidden_themes:
            if theme and theme in text:
                return True, f"forbidden_theme: {theme!r}"
        return False, ""

    def analyze_thread_series(
        self,
        results: list[dict[str, Any]],
        series_id: str,
    ) -> dict[str, Any]:
        """特定 series_id の投稿結果を分析する。"""
        series_posts = [r for r in results if r.get("series_id") == series_id]
        if not series_posts:
            return {"series_id": series_id, "post_count": 0, "posts": [], "hook_metrics": {}}

        sorted_posts = sorted(series_posts, key=lambda r: self._safe_int(r.get("post_index", 0)))
        hook = next((r for r in sorted_posts if self._safe_int(r.get("post_index", -1)) == 0), None)

        return {
            "series_id": series_id,
            "post_count": len(sorted_posts),
            "posts": sorted_posts,
            "hook_metrics": self._aggregate_metrics([hook]) if hook else {},
            "overall_metrics": self._aggregate_metrics(sorted_posts),
            "dropoff": self._analyze_dropoff(sorted_posts),
        }

    def analyze_hook_effectiveness(
        self,
        results: list[dict[str, Any]],
        *,
        account_id: str | None = None,
    ) -> dict[str, Any]:
        """hook投稿（post_index=0）と後続投稿のエンゲージメント比較。"""
        filtered = self._filter(results, account_id=account_id, platform=None)
        hooks = [r for r in filtered if self._safe_int(r.get("post_index", -1)) == 0]
        non_hooks = [r for r in filtered if self._safe_int(r.get("post_index", -1)) > 0]

        return {
            "account_id": account_id,
            "hook_count": len(hooks),
            "non_hook_count": len(non_hooks),
            "hook_metrics": self._aggregate_metrics(hooks) if hooks else {},
            "non_hook_metrics": self._aggregate_metrics(non_hooks) if non_hooks else {},
        }

    def _analyze_dropoff(self, sorted_posts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """投稿インデックスごとのエンゲージメント推移を返す。"""
        dropoff = []
        for post in sorted_posts:
            idx = self._safe_int(post.get("post_index", 0))
            eng = self._engagement_score(post)
            dropoff.append({
                "post_index": idx,
                "post_role": post.get("post_role", ""),
                "engagement_score": round(eng, 4),
                "likes": self._safe_int(post.get("likes", 0)),
                "impressions": self._safe_int(post.get("impressions", 0)),
            })
        return dropoff
