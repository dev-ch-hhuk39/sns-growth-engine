# pdca_orchestrator

posted_results → 分析 → improvement_suggestions → 次回 generation_jobs 候補（Phase 7.E）。

## 概要

- posted_results を account_id / platform / days でフィルタして分析
- single_post / thread_series / reference_based / video_clip_reference を比較
- thread_series では hook_effectiveness と dropoff を分析
- improvement_suggestions は常に `status=WAITING_REVIEW`（自動適用禁止）
- learning_rules.active は常に `false`（人間承認なしの自動変更禁止）
- 次回 generation_jobs 候補は `status=PLANNED`（自動実行禁止）
- beauty_account は draft_only → mock/fixture 分析のみ

## フロー

```
posted_results
  → _filter_results() (account_id / platform / days)
  → _compare_content_types()
  → PostResultAnalyzer (hook / dropoff)
  → _generate_improvement_suggestions()  → WAITING_REVIEW
  → _generate_next_jobs()  → PLANNED
```

## 改善提案タイプ

| type | トリガー |
|------|---------|
| content_mix_ratio | 特定 content_type のER が最高 |
| hook_improvement | hook ER < 非hook ER × 0.8 |
| hook_strength | hook が効果的 |
| thread_dropoff | 最初→最後の impressions 減少率 > 70% |

## 使い方

```bash
# dry-run mock
python scripts/run_pdca_cycle.py --account-id night_scout --platform x --days 7 --dry-run --mock --generate-next-plan

# 改善提案 JSON 出力
python scripts/run_pdca_cycle.py --account-id night_scout --platform x --days 30 --dry-run --mock --output-json
```

## 安全ルール

- improvement_suggestions は全て WAITING_REVIEW（自動適用絶対禁止）
- learning_rules.active は false のまま（人間承認が必要）
- next_generation_jobs は PLANNED（自動実行禁止）
- prompt / code の自動書き換え禁止
- posted_results への本番投稿結果の自動保存禁止
- beauty_account は draft_only → 実投稿学習なし
