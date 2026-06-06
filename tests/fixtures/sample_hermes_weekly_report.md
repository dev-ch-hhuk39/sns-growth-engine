# Hermes Weekly Analysis Report - 2026-W23

**Generated**: 2026-06-06T10:00:00+00:00  
**Account**: night_scout  
**Analysis Period**: 2026-05-30 〜 2026-06-05  

---

## Executive Summary

今週は video_clip_reference モードで3件の投稿を生成し、うち2件が READY 昇格しました。
テキストポリシー違反率（15.0%）が改善目標（10%未満）を超えており、プロンプト調整を推奨します。

---

## Performance Metrics

| 指標 | 今週 | 先週 | 差分 |
|------|------|------|------|
| posted_count | 3 | 2 | +1 |
| avg_likes | 38.5 | 31.2 | +23.4% |
| avg_views | 950 | 820 | +15.9% |
| avg_engagement_rate | 1.8% | 1.5% | +20.0% |
| text_policy_fail_rate | 15.0% | 8.0% | +7.0pp |

---

## Improvement Suggestions

### 1. テキストポリシー違反率の改善（HIGH）

**現状**: text_policy_status=FAIL が 15.0%  
**提案**: 生成プロンプトに X 投稿 120 字制約を強化  
**根拠**: 先週 8.0% → 今週 15.0% に悪化  
**期待効果**: 違反率を 10% 未満に抑制  

### 2. フック文の強化（MEDIUM）

**現状**: avg_engagement_rate 1.8%（目標 2.0%）  
**提案**: 夜職系ターゲットに刺さる冒頭フレーズの例示追加  
**根拠**: 直近投稿でフック文の反応が低い  
**期待効果**: エンゲージメント率 +20%  

---

## Rights Review Status

- rights_review_required=true: 1件（WAITING_REVIEW）
- ref-yt-003: rights_status=unknown → 人間レビューが必要

---

## Next Actions

1. `review_improvement_suggestions.py` で提案を確認
2. `approve_learning_rule.py --suggestion-id sug-abc12345 --confirm-approve` で承認
3. `review_queue.py --account-id night_scout` で権利レビュー対象を確認

---

*このレポートは Hermes Agent が生成しました。承認なしにプロンプトを自動変更しないでください。*
