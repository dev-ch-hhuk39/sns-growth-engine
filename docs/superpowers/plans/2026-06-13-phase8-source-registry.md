# Phase 8: End-to-End Operational Readiness + Source Registry

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Phase 7の5オーケストレーターを実運用直前として接続・補強し、外部参考アカウント・動画ソースを管理するSource Account / Video Source Registryを追加する。

**Architecture:** source_registryを基盤に既存5モジュール（content_mix_planner, source_account_collector, media_ingestion_pipeline, end_to_end_preflight, pdca_orchestrator）を拡張。実API/実投稿/外部download禁止。beauty_accountはdraft_only維持。

**Tech Stack:** Python 3.13, Google Sheets API, JSON fixtures, dry-run only

---

## 実行順（依存関係）

1. source_registry (全依存元)
2. 既存5モジュール更新 (source_registry参照追加)
3. 新規CLIスクリプト
4. Sheets schema統合
5. 新規テスト11本 + 既存テスト更新
6. テスト実行・修正ループ
7. ドキュメント更新
8. CLAUDE.md更新
9. commit/push

## ファイルマップ

### 新規作成
- `config/source_accounts/default_sources.json`
- `tests/fixtures/sample_source_registry.json`
- `src/reference/source_registry.py`
- `scripts/manage_source_accounts.py`
- `scripts/plan_source_collection.py`
- `scripts/preflight_real_llm_generation.py`
- `scripts/check_beauty_activation_readiness.py`
- `scripts/test_source_account_registry.py`
- `scripts/test_phase8_source_registry_to_collection.py`
- `scripts/test_phase8_sheets_schema.py`
- `scripts/test_phase8_content_mix_to_jobs.py`
- `scripts/test_phase8_source_to_reference_generation.py`
- `scripts/test_phase8_media_to_preflight.py`
- `scripts/test_phase8_end_to_end_preflight_matrix.py`
- `scripts/test_phase8_pdca_to_next_plan.py`
- `scripts/test_real_llm_generation_preflight.py`
- `scripts/test_phase8_real_llm_generation_safety.py`
- `scripts/test_beauty_activation_readiness.py`
- `docs/source-account-registry.md`
- `docs/real-llm-generation-test.md`
- `docs/beauty-account-activation-checklist.md`
- `docs/sheets-schema.md`

### 更新
- `src/generation/content_mix_planner.py` (generation_jobs候補出力追加)
- `src/reference/source_account_collector.py` (source_registry連携)
- `src/media/media_ingestion_pipeline.py` (source_id/source_url対応)
- `scripts/preflight_end_to_end_publish.py` (source rights確認追加)
- `src/learning/pdca_orchestrator.py` (source別分析・次回plan追加)
- `scripts/setup_and_verify.py` (Phase 8 tabsスキーマ追加)
- `scripts/check_pipeline_integrity.py` (source_registry確認追加)
- `CLAUDE.md` (global policy参照追加)
- `docs/roadmap.md`, `docs/operation-runbook.md`, `docs/manual-smoke-test-sequence.md`
- `docs/emergency-rollback.md`, `docs/content-mix-planner.md`
- `docs/source-account-collector.md`, `docs/media-ingestion-pipeline.md`
- `docs/end-to-end-publish-preflight.md`, `docs/pdca-orchestrator.md`
- `docs/beauty-account-roadmap.md`
