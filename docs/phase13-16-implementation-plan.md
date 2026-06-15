# Phase 13-16 Implementation Plan

## 概要

Phase 9-12 で完成した Source-to-Post パイプラインを、本番運用可能な状態に引き上げる。

- **Phase 13**: Production Media Source Pipeline 基盤整備 ← **完了**
- **Phase 14**: Scheduled Execution (スケジューラー / 自動実行)
- **Phase 15**: Monitoring / Alerts (実行ログ / アラート)
- **Phase 16**: Full Production Integration (E2E テスト / 本番運用開始)

---

## Phase 13 — Production Media Source Pipeline ✅ 完了

### 目的

ソース候補の登録・管理・審査フローと、本番投稿 CLI を整備する。

### 完了した実装

| ファイル | 内容 |
|---|---|
| `src/reference/fetchers/tool_doctor.py` | yt-dlp / ffmpeg / youtube-transcript-api 診断 |
| `src/storage/pipeline_store.py` | パイプライン出力の JSON 保存 |
| `src/reference/fetchers/article_fetcher.py` | note/article URL フェッチャー |
| `src/reference/article_reference_normalizer.py` | 記事 → リファレンス正規化 |
| `config/source_accounts/production_sources.example.json` | 54件ソース候補テンプレート |
| `scripts/add_source_candidate.py` | ソース候補追加 CLI (dry_run 必須) |
| `scripts/update_source_status.py` | ソースステータス更新 CLI |
| `scripts/review_source_candidates.py` | ソース候補一覧 CLI |
| `scripts/save_pipeline_outputs.py` | パイプライン出力保存 CLI |
| `scripts/publish_threads_post.py` | Threads 投稿 CLI (dry_run デフォルト) |
| `scripts/publish_x_post.py` | X 投稿 CLI (dry_run デフォルト) |
| `scripts/check_source_fetcher_tools.py` | ToolDoctor 実行 CLI |
| `scripts/run_phase13_smoke_plan.py` | Phase 13 スモークプラン |
| `scripts/test_phase13_*.py` (7本) | テスト (148 PASS / 0 FAIL) |

---

## Phase 14 — Scheduled Execution

### 目的

特定の時間帯にソース収集 → コンテンツ生成 → 投稿を自動実行する。

### 設計方針

- dry_run=True がデフォルト、スケジューラー起動時も同様
- 実行ログは `output/pipeline_runs/<run_id>/` に保存
- 1アカウント = 1スケジューラープロセス（競合防止）
- 実行失敗は次回スケジュールに持ち越す（リトライなし）

### 実装予定ファイル

| ファイル | 内容 |
|---|---|
| `src/scheduler/scheduler.py` | APScheduler または cron ベースの実行管理 |
| `src/scheduler/job_runner.py` | ソース→生成→投稿ジョブ実行 |
| `scripts/start_scheduler.py` | スケジューラー起動 CLI |
| `scripts/test_phase14_scheduler.py` | テスト |

### 実装順序

1. `job_runner.py` — SourceToPostOrchestrator をラップしたジョブ定義
2. `scheduler.py` — cron 式 or 固定間隔でジョブを起動
3. `start_scheduler.py` — dry_run=True でのスケジューラー起動確認
4. テスト作成・FAIL=0

---

## Phase 15 — Monitoring / Alerts

### 目的

投稿の成功/失敗を追跡し、問題を早期発見する。

### 設計方針

- PipelineStore の出力を元にサマリーを生成
- 失敗率が閾値を超えた場合のみアラート
- シークレット・本文・個人情報はログに出力しない

### 実装予定ファイル

| ファイル | 内容 |
|---|---|
| `src/monitoring/pipeline_reporter.py` | run サマリー生成 |
| `src/monitoring/alert_handler.py` | 閾値判定・アラート出力 |
| `scripts/generate_pipeline_report.py` | レポート生成 CLI |
| `scripts/test_phase15_monitoring.py` | テスト |

---

## Phase 16 — Full Production Integration

### 目的

全コンポーネントを統合し、beauty_account 含む E2E テストを完了させ、本番運用を開始する。

### 本番運用開始チェックリスト

- [ ] Phase 13 全テスト FAIL=0
- [ ] Phase 14 スケジューラー dry_run テスト PASS
- [ ] Phase 15 モニタリング dry_run テスト PASS
- [ ] 全ソースの実 URL / handle 設定完了
- [ ] rights_policy の審査完了 (`unknown` → `reference_only` / `permission_granted` 等)
- [ ] ToolDoctor で全ツール OK
- [ ] beauty_account ガード最終確認 (active=false のまま)
- [ ] run_phase13_smoke_plan で E2E dry_run PASS
- [ ] PUBLISH_ENABLED / ALLOW_REAL_* フラグを設定して手動1件投稿確認

### 実装予定ファイル

| ファイル | 内容 |
|---|---|
| `scripts/test_phase16_e2e_production.py` | E2E テスト |
| `docs/manual-smoke-test-sequence.md` | 手動スモークテスト手順 |

---

## 共通方針

### dry_run の扱い

全 CLI は `dry_run=True` がデフォルト。`--no-dry-run` を明示した場合のみ実 write/post を行う。

### beauty_account

- Phase 16 以降も `active=false` を維持
- 投稿 CLI から BLOCKED
- allow_cut=false / allow_upload=false は変更禁止

### テスト方針

- check() / results[] パターンで統一
- `mock=True, dry_run=True` でのテストを基本とする
- 実 API / 実 fetch / 実 download は confirm フラグ必須

### コミットメッセージ規約

```
feat: finalize production media source pipeline
```

このメッセージで Phase 13 完了コミットを行う。
