# Phase 13-16 テストマトリクス

## Phase 13 — Production Media Source Pipeline

| テストファイル | 対象コンポーネント | テスト数 | 状態 |
|---|---|---|---|
| test_phase13_tool_doctor.py | ToolDoctor | 28 | ✅ PASS |
| test_phase13_pipeline_store.py | PipelineStore | 15 | ✅ PASS |
| test_phase13_article_fetcher.py | ArticleFetcher | 21 | ✅ PASS |
| test_phase13_article_normalizer.py | ArticleReferenceNormalizer | 18 | ✅ PASS |
| test_phase13_production_sources.py | production_sources.example.json | 28 | ✅ PASS |
| test_phase13_source_lifecycle_cli.py | add/update/review CLIs | 23 | ✅ PASS |
| test_phase13_smoke_plan.py | SmokePlan / Publisher CLIs | 15 | ✅ PASS |

**合計: 148 PASS / 0 FAIL**

### Phase 13 テストカバレッジ

| カバー項目 | テストファイル |
|---|---|
| ToolCheckResult dataclass | tool_doctor |
| NOT_INSTALLED → exit_code=0 (WARN not FAIL) | tool_doctor |
| PipelineStore dry_run/real save | pipeline_store |
| PipelineStore load / list_runs | pipeline_store |
| ArticleFetcher mock fetch | article_fetcher |
| ArticleFetcher confirm_fetch gate | article_fetcher |
| ArticleFetcher allow_network_fetch gate | article_fetcher |
| ArticleNormalizer abstract generation | article_normalizer |
| ArticleNormalizer reference_post_id | article_normalizer |
| normalize_articles フィルタリング | article_normalizer |
| JSON valid parse | production_sources |
| 54件エントリ数 | production_sources |
| active=False 全件 | production_sources |
| fetch_enabled=False 全件 | production_sources |
| beauty_account subject_policy | production_sources |
| beauty_account allow_cut/upload=False | production_sources |
| TikTok/X beauty=disabled | production_sources |
| URL 破損なし | production_sources |
| add_source_candidate dry_run | source_lifecycle_cli |
| add_source_candidate no-dry-run | source_lifecycle_cli |
| 重複 source_id エラー | source_lifecycle_cli |
| update_source_status dry_run | source_lifecycle_cli |
| fetch_enabled safety gate | source_lifecycle_cli |
| review_source_candidates フィルタ | source_lifecycle_cli |
| SmokePlan 4ステップ通過 | smoke_plan |
| publish_x_post dry_run | smoke_plan |
| publish_x_post 280文字制限 | smoke_plan |
| publish_threads_post dry_run | smoke_plan |
| beauty_account publisher BLOCKED | smoke_plan |

## Phase 9-11 (継続確認)

| テストファイル | テスト数 | 状態 |
|---|---|---|
| test_phase10_original_hypothesis_generation.py | 31 | ✅ PASS |
| test_phase10_pdca_full_loop.py | 11 | ✅ PASS |
| test_phase10_publishers_safety.py | 14 | ✅ PASS |
| test_phase10_threads_publisher.py | 7 | ✅ PASS |
| test_phase10_x_publisher.py | 5 | ✅ PASS |
| test_phase11_source_to_post_orchestrator.py | 23 | ✅ PASS |

## Phase 14-16 (未実装・テスト計画)

### Phase 14 — Scheduled Execution

| テスト | 対象 | 優先度 |
|---|---|---|
| スケジューラー起動 dry_run | scheduler.py | 高 |
| cron 式バリデーション | scheduler | 中 |
| 複数ソースのシーケンシャル実行 | scheduler | 高 |

### Phase 15 — Monitoring / Alerts

| テスト | 対象 | 優先度 |
|---|---|---|
| FAIL 件数アラートしきい値 | alert.py | 高 |
| PipelineStore からのサマリ生成 | reporting.py | 中 |

### Phase 16 — Full Production Integration

| テスト | 対象 | 優先度 |
|---|---|---|
| E2E dry_run (全ソース) | integration | 高 |
| beauty_account ガード確認 | integration | 必須 |
| 投稿フラグ OFF での誤投稿なし | integration | 必須 |

## テスト実行方法

```bash
# Phase 13 全テスト
for f in scripts/test_phase13_*.py; do python3 "$f"; done

# 全テスト（Phase 9-13）
for f in scripts/test_phase10_*.py scripts/test_phase11_*.py scripts/test_phase13_*.py; do
  python3 "$f" 2>&1 | tail -2
done

# SmokePlan
python3 scripts/run_phase13_smoke_plan.py --account-id night_scout --platform x
```
