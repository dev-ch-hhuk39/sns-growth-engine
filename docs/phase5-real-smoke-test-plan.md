# Phase 5 Real Smoke Test Plan

## 概要

Phase 5.0〜5.6 は実運用直前の最後の土台固め。
小規模実テストを安全に進めるためのrunbook・オーケストレーター・learning loopを整備する。

**作業ディレクトリ**: `/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2`
**触らないフォルダ**: `使ってない_過去/`・`Documents/claudecodeプロジェクトディレクトリ/`・既存3プロジェクト

## フェーズ構成

| Phase | 内容 |
|-------|------|
| 5.0 | Real Smoke Test Orchestrator |
| 5.1 | Cloudflare 実スモーク手順 |
| 5.2 | Cloudinary 小規模アップロード手順 |
| 5.3 | X 1件投稿直前手順 |
| 5.4 | posted_results → learning loop |
| 5.5 | GitHub Actions dry-run workflow |
| 5.6 | 最終運用Runbook |

## 安全制約（全Phase共通）

以下は **絶対に行わない**:

- SNS本番投稿 / X API投稿 / Threads API投稿
- Cloudflare API実呼び出し
- Cloudinary実アップロード
- GitHub Actions実行（ローカルから）
- PUBLISH_ENABLED=true
- ALLOW_REAL_X_POST=true
- ALLOW_TRANSCRIPTION_API=true
- ALLOW_CLOUDINARY_UPLOAD=true
- learning_rules.active=true の自動設定
- prompt/code の自動書き換え
- queue.status=POSTED への変更
- posted_results への本番投稿結果保存

## Phase 5.0: Smoke Test Orchestrator

### スクリプト

```bash
# dry-run（実行安全）
python scripts/run_real_smoke_plan.py --step all
python scripts/run_real_smoke_plan.py --step cloudflare
python scripts/run_real_smoke_plan.py --step cloudinary
python scripts/run_real_smoke_plan.py --step x
python scripts/run_real_smoke_plan.py --step all --account-id night_scout
```

### 判定基準

| 判定 | 意味 |
|------|------|
| `READY` | 認証情報あり、実行フラグ有効（慎重に実行） |
| `READY_FOR_MANUAL_SMOKE` | 認証情報あり、実APIは無効（フラグ設定後に実行可） |
| `NOT_READY` | 認証情報不足 |
| `BLOCKED` | 安全ガードにより実行不可 |

## Phase 5.1: Cloudflare

→ `docs/cloudflare-transcription-runbook.md` 参照

## Phase 5.2: Cloudinary

→ `docs/cloudinary-upload-runbook.md` 参照

## Phase 5.3: X投稿

→ `docs/x-real-post-final-checklist.md`・`docs/x-media-post-smoke-test.md` 参照

## Phase 5.4: Learning Loop

→ `docs/post-results-learning-loop.md` 参照

## Phase 5.5: GitHub Actions

→ `docs/github-actions-dry-run-workflow.md` 参照

## Phase 5.6: 運用Runbook

→ `docs/operation-runbook.md`・`docs/manual-smoke-test-sequence.md`・`docs/emergency-rollback.md` 参照

## 実行順序（次回ユーザーが.envを設定した後）

1. `.env` に認証情報を設定
2. `python scripts/run_real_smoke_plan.py --step all` で準備状況確認
3. `docs/manual-smoke-test-sequence.md` の手順に従い1ステップずつ実行
4. 各ステップ後に安全フラグを `false` に戻す
5. `python scripts/check_pipeline_integrity.py --account-id night_scout` で整合性確認
