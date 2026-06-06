"""
improvement_suggester.py - プロンプト改善提案生成（Phase 4.0）

PerformanceAnalyzer の出力を受け取り、改善提案を生成する。
生成された提案は status=WAITING_REVIEW で返され、人間の承認が必要。

禁止事項:
  - active=true の自動設定（人間承認なしの自動適用）
  - SNS本番投稿
  - Sheets 直接書き込み（import_improvement_suggestions.py 経由のみ）
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


class ImprovementSuggester:
    """ImprovementSuggester - パフォーマンスデータから改善提案を生成。

    全提案は status=WAITING_REVIEW で出力する。active=true の自動設定は禁止。
    """

    # 閾値定義
    TEXT_POLICY_FAIL_WARN_THRESHOLD = 0.10     # 10% 以上で提案
    RIGHTS_REVIEW_WARN_THRESHOLD = 0.20         # 20% 以上で提案
    LOW_ENGAGEMENT_THRESHOLD = 0.02             # 2% 未満で提案
    MIN_POSTED_COUNT_FOR_ANALYSIS = 3           # 最低投稿数

    def suggest(
        self,
        metrics: dict[str, Any],
        *,
        source: str = "performance_analyzer",
    ) -> list[dict[str, Any]]:
        """メトリクスから改善提案リストを生成する。

        Args:
            metrics: PerformanceAnalyzer.analyze() の出力
            source: 提案ソース（performance_analyzer / hermes / manual）

        Returns:
            改善提案リスト（各要素は prompt_improvement_suggestions タブの1行に対応）
        """
        suggestions: list[dict[str, Any]] = []
        account_id = metrics.get("account_id", "unknown")
        posted_count = int(metrics.get("posted_count", 0))

        # 最低投稿数チェック
        if posted_count < self.MIN_POSTED_COUNT_FOR_ANALYSIS:
            return []

        # テキストポリシー失敗率チェック
        fail_rate = float(metrics.get("text_policy_fail_rate", 0.0))
        if fail_rate >= self.TEXT_POLICY_FAIL_WARN_THRESHOLD:
            suggestions.append(
                self._make_suggestion(
                    account_id=account_id,
                    source=source,
                    suggestion_type="prompt_change",
                    current_behavior=f"queue の text_policy_status=FAIL 率: {fail_rate:.1%}",
                    suggested_change=(
                        "生成プロンプトに「X投稿は120字以内、Threads投稿は600字以内」の制約を強化する。"
                        "文字数カウント例示をプロンプトに追加することを検討してください。"
                    ),
                    reason=f"text_policy_fail_rate={fail_rate:.1%} が閾値 {self.TEXT_POLICY_FAIL_WARN_THRESHOLD:.0%} を超過",
                    expected_impact="テキストポリシー違反率 50% 削減を目標",
                    priority="high" if fail_rate >= 0.20 else "medium",
                )
            )

        # 権利レビュー要求率チェック
        rights_rate = float(metrics.get("rights_review_required_rate", 0.0))
        if rights_rate >= self.RIGHTS_REVIEW_WARN_THRESHOLD:
            suggestions.append(
                self._make_suggestion(
                    account_id=account_id,
                    source=source,
                    suggestion_type="rule_addition",
                    current_behavior=f"queue の rights_review_required=true 率: {rights_rate:.1%}",
                    suggested_change=(
                        "reference_posts 収集時に rights_status を事前チェックする処理を追加する。"
                        "または収集対象をライセンス明示動画に限定する運用ルールの追加を検討してください。"
                    ),
                    reason=f"rights_review_required_rate={rights_rate:.1%} が閾値 {self.RIGHTS_REVIEW_WARN_THRESHOLD:.0%} を超過",
                    expected_impact="権利レビュー工数 30% 削減を目標",
                    priority="medium",
                )
            )

        # エンゲージメント率チェック
        eng_rate = float(metrics.get("avg_engagement_rate", 0.0))
        avg_views = float(metrics.get("avg_views", 0.0))
        if avg_views > 0 and eng_rate < self.LOW_ENGAGEMENT_THRESHOLD:
            suggestions.append(
                self._make_suggestion(
                    account_id=account_id,
                    source=source,
                    suggestion_type="prompt_change",
                    current_behavior=f"平均エンゲージメント率: {eng_rate:.2%} (avg_views={avg_views:.0f})",
                    suggested_change=(
                        "フック文の強化: 冒頭1〜2文でターゲットペルソナの課題を直接刺すよう"
                        "プロンプトの hook_type 指示を見直してください。"
                    ),
                    reason=f"avg_engagement_rate={eng_rate:.2%} が低下（閾値: {self.LOW_ENGAGEMENT_THRESHOLD:.0%}）",
                    expected_impact="エンゲージメント率 20% 改善を目標",
                    priority="high" if eng_rate < 0.01 else "medium",
                )
            )

        return suggestions

    def _make_suggestion(
        self,
        *,
        account_id: str,
        source: str,
        suggestion_type: str,
        current_behavior: str,
        suggested_change: str,
        reason: str,
        expected_impact: str,
        priority: str,
        target_template: str = "",
    ) -> dict[str, Any]:
        return {
            "suggestion_id": f"sug-{_short_uuid()}",
            "account_id": account_id,
            "created_at": _now(),
            "source": source,
            "suggestion_type": suggestion_type,
            "target_template": target_template,
            "current_behavior": current_behavior,
            "suggested_change": suggested_change,
            "reason": reason,
            "expected_impact": expected_impact,
            "priority": priority,
            "status": "WAITING_REVIEW",
            "reviewed_by": "",
            "reviewed_at": "",
            "notes": "",
        }
