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
| test_phase13_production_sources_real_urls.py | user-provided real URL reflection | 1 | ✅ PASS |
| test_phase13_media_asset_storage.py | media_assets planning / PipelineStore dry-run | 3 | ✅ PASS |
| test_phase13_video_clip_execution.py | clip confirm gate | 3 | ✅ PASS |
| test_phase13_media_post_preflight.py | media post preflight | 3 | ✅ PASS |
| test_phase13_query_source_support.py | trend query sources | 5 | ✅ PASS |
| test_phase13_article_source_support.py | note/article source policy | 5 | ✅ PASS |
| test_phase13_source_concept_matching.py | subject_policy / concept safety | 4 | ✅ PASS |
| test_phase13_fetcher_production_paths.py | fetcher mock and confirm gate | 2 | ✅ PASS |
| test_phase13_source_to_post_production_path.py | orchestrator production dry-run path | 4 | ✅ PASS |
| test_phase13_generation_production.py | draft/review-only generation | 3 | ✅ PASS |
| test_phase13_publishers_production_safety.py | publisher CLI safety gates | 4 | ✅ PASS |
| test_phase13_pdca_production_loop.py | PDCA review-only suggestions | 3 | ✅ PASS |

**Phase 13 legacy core total: 148 PASS / 0 FAIL**  
**Phase 9-13 regression + added tests: 39 files PASS / 0 FAIL**  
**Dry-run / BLOCKED command sweep: 35 commands PASS / 0 FAIL**

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
| user-provided 54 URLs reflected | production_sources_real_urls |
| `REPLACE_WITH_REAL_*` absent | production_sources_real_urls |
| query source counts and fetch disabled | query_source_support |
| note article extraction fields / copy block | article_source_support |
| media asset creation from raw image/video URLs | media_asset_storage |
| media preflight blocks unknown/plan_only media | media_post_preflight |
| clip execution blocks missing confirm | video_clip_execution |
| confirmなしfetch BLOCKED | fetcher_production_paths |
| confirmなしpost BLOCKED | publishers_production_safety |
| PDCA suggestions `auto_apply=false` | pdca_production_loop |

## Phase 9-11 (継続確認)

| テストファイル | テスト数 | 状態 |
|---|---|---|
| test_phase10_original_hypothesis_generation.py | 31 | ✅ PASS |
| test_phase10_pdca_full_loop.py | 11 | ✅ PASS |
| test_phase10_publishers_safety.py | 14 | ✅ PASS |
| test_phase10_threads_publisher.py | 7 | ✅ PASS |
| test_phase10_x_publisher.py | 5 | ✅ PASS |
| test_phase11_source_to_post_orchestrator.py | 23 | ✅ PASS |

## Dry-run / BLOCKED Sweep

| Area | Result |
|---|---|
| ToolDoctor dry-run | ✅ PASS |
| Source account validate/review dry-run | ✅ PASS |
| Mock source fetch for X/YouTube/note/TikTok | ✅ PASS |
| `--fetch` without `--confirm-fetch` | ✅ BLOCKED |
| Media preflight/download dry-run | ✅ PASS |
| `--download` without `--confirm-download` | ✅ BLOCKED |
| Clip dry-run | ✅ PASS |
| `--cut` without `--confirm-cut` | ✅ BLOCKED |
| Upload dry-run | ✅ PASS |
| `--upload` without `--confirm-upload` | ✅ BLOCKED |
| Source-to-post pipeline mock dry-run | ✅ PASS / publish BLOCKED |
| Publisher mock/confirm dry-run | ✅ PASS |
| Real post without `--confirm-post` | ✅ BLOCKED |
| Real smoke plan dry-run readiness | ✅ PASS with environment NOT_READY WARN |
| Posted results mock import dry-run | ✅ PASS |
| PDCA cycle mock dry-run | ✅ PASS |

## Final Rollout Recheck (2026-06-17)

| Check | Result |
|---|---|
| PR created | ✅ https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/1 |
| Merge前安全監査 | ✅ 17 / 17 PASS |
| Merge前 minimum tests | ✅ 11 / 11 PASS |
| Phase9-13 regression | ✅ 39 / 39 PASS |
| dry-run / BLOCKED checks | ✅ 22 / 22 PASS |
| Secret/media artifact diff scan | ✅ no `.env`, token/cookie/secret, image/video artifacts in PR diff |
| Real fetch/download/cut/upload/post | ✅ not executed |
| First smoke docs | ✅ `docs/manual-smoke-test-sequence.md`, `docs/production-launch-checklist.md` |

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
