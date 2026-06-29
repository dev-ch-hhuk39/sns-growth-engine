# Phase 13-16 テストマトリクス

## Threads Queue Worker Release (2026-06-24)

| テストファイル | 対象 | 結果 |
|---|---|---|
| test_process_threads_queue.py | worker safety gates | PASS 8 / FAIL 0 |
| test_threads_queue_duplicate_guard.py | duplicate guard | PASS 5 / FAIL 0 |
| test_posted_results_integrity.py | posted_results schema / verifier constraints | PASS 7 / FAIL 0 |
| test_import_threads_metrics_manual.py | metrics import dry-run | PASS 4 / FAIL 0 |
| test_refill_threads_queue.py | refill safety | PASS 8 / FAIL 0 |
| test_threads_queue_worker_workflow.py | manual-only GitHub Actions worker | PASS 11 / FAIL 0 |
| test_true_dry_run_no_setup_all.py | queue/refill dry-run read-only guarantee | PASS 7 / FAIL 0 |
| test_live_verify_schema_strictness.py | strict live verifier checks | PASS 10 / FAIL 0 |
| test_metrics_import_dry_run_no_sheets_connection.py | metrics dry-run avoids Sheets connection | PASS 3 / FAIL 0 |
| test_content_workflows_safety.py | workflow safety including worker | PASS 9 / FAIL 0 |
| test_beauty_account_block.py | beauty block including worker/refill | PASS 9 / FAIL 0 |
| test_x_disabled_mode.py | X disabled including worker/refill | PASS 9 / FAIL 0 |

Required local test sweep on 2026-06-24: PASS.
Live local Sheets runtime verification after this release: pending due to approval system out-of-credits. GitHub Actions dry-run was attempted and stopped before queue processing because repository Sheets secrets were missing.

## Phase 13 — Production Media Source Pipeline

| テストファイル | 対象コンポーネント | テスト数 | 状態 |
|---|---|---|---|
| test_phase13_tool_doctor.py | ToolDoctor | 28 | ✅ PASS |
| test_phase13_pipeline_store.py | PipelineStore | 15 | ✅ PASS |
| test_phase13_article_fetcher.py | ArticleFetcher | 21 | ✅ PASS |
| test_phase13_article_normalizer.py | ArticleReferenceNormalizer | 18 | ✅ PASS |
| test_phase13_production_sources.py | production_sources.example.json | 28 | ✅ PASS |
| test_phase13_source_lifecycle_cli.py | add/update/review CLIs | 23 | ✅ PASS |
| test_phase13_smoke_plan.py | SmokePlan / Publisher CLIs | 18 | ✅ PASS |
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
| run_real_smoke_plan `--platform threads` uses Threads preflight | smoke_plan |
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

## Follow-up Recheck (2026-06-17)

| Check | Result |
|---|---|
| Follow-up PR | ⚠️ https://github.com/dev-ch-hhuk39/sns-growth-engine/pull/2 |
| PR #2 merge attempt | ⚠️ blocked by connector approval credits; no direct main push attempted |
| `run_real_smoke_plan.py --platform threads` | ✅ Threads preflight branch confirmed; credential-free env returns NOT_READY by design |
| `test_phase13_smoke_plan.py` | ✅ 18 / 18 PASS |
| `test_phase13_publishers_production_safety.py` | ✅ 4 / 4 PASS |

## Source Registry Integration Recheck (2026-06-29)

| Check | Result |
|---|---|
| `default_sources.json` truth source | ✅ 59 sources / active 6 / fetch_enabled 0 |
| `production_sources.example.json` source count | ✅ 91 sources / active 0 / fetch_enabled 0 |
| `recovered_shared_sources.json` | ✅ 3 recovered Threads sources |
| Placeholder URL/handle audit | ✅ `test_phase13_production_sources_real_urls.py` PASS |
| Beauty target safety | ✅ `target_account_ids=["beauty_account"]`; no `beauty_future` target |
| Beauty reference-only safety | ✅ `rights_policy=reference_only`, `use_policy=REFERENCE_ONLY`, `can_reuse_media=false` |
| `source_rows()` safety columns | ✅ source_accounts/reference_sources both emit review/track/use/reuse safety fields |
| seed dry-run all | ✅ 59 source_accounts / 33 reference_sources / no Sheets write |
| seed apply without confirm | ✅ dry-run扱い / no Sheets write |
| `test_seed_source_registry.py` | ✅ 10 / 10 PASS |
| `test_source_registry_verify_checks.py` | ✅ 11 / 11 PASS |
| Selected Phase13 regression | ✅ PASS / FAIL 0 |
| Selected Phase10-11 queue/publisher safety | ✅ PASS / FAIL 0 |

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
