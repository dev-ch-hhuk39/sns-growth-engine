# 日常運用 Runbook

## 作業ディレクトリ

```
/Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2
```

**触らないフォルダ**:
- `使ってない_過去/SNS自動投稿システム/` (zip退避済み)
- `Documents/claudecodeプロジェクトディレクトリ/` (旧フォルダ)
- 既存3プロジェクト（夜職_x / 夜職_threads / ライバー）

**開発環境**: Claude Code（claude-hr経由）/ Headroom v0.23.0 導入済み

## 1. 日常運用フロー（週次）

```bash
# 環境確認
python scripts/preflight_check.py --quick
python scripts/check_pipeline_integrity.py --account-id night_scout
python scripts/check_learning_integrity.py --account-id night_scout

# reference収集（dry-run）
python scripts/collect_references.py --account-id night_scout --dry-run

# 下書き生成（dry-run）
python scripts/generate_drafts.py --account-id night_scout --dry-run

# キューレビュー
python scripts/review_queue.py --account-id night_scout --status WAITING_REVIEW
```

## 1-b. Threads トークン管理（月次）

Threads アクセストークンは 60日で失効。以下の手順で月次確認・refresh する。

```bash
# トークン状態確認（値は表示されない）
python3 scripts/refresh_threads_token.py --account-id night_scout --status
python3 scripts/refresh_threads_token.py --account-id liver_manager --status

# dry-run で refresh 確認（API 未呼び出し）
python3 scripts/refresh_threads_token.py --account-id night_scout --dry-run

# 実 refresh（残り45日以内になったら実行）
python3 scripts/refresh_threads_token.py --account-id night_scout --confirm-refresh
python3 scripts/refresh_threads_token.py --account-id liver_manager --confirm-refresh
```

自動化: `.github/workflows/refresh-threads-tokens.yml` が毎週日曜 11:00 JST に実行。  
詳細: `docs/threads-token-refresh-automation.md`

## 2. Reference収集

```bash
# X参照ポストの収集（dry-run）
python scripts/collect_references.py --account-id night_scout --dry-run

# 分析
python scripts/analyze_references.py --account-id night_scout

# 参照ポストのスコアリング確認
python scripts/review_improvement_suggestions.py --account-id night_scout
```

## 3. Video Pipeline

```bash
# video pipeline preflight（実ダウンロードなし）
python scripts/preflight_video_real_test.py --mock

# video clip分析（dry-run）
python scripts/analyze_video_clips.py --account-id night_scout --dry-run

# ビデオリファレンス確認
python scripts/check_pipeline_integrity.py --account-id night_scout
```

## 4. Review Queue

```bash
# WAITING_REVIEW の確認
python scripts/review_queue.py --account-id night_scout --status WAITING_REVIEW

# READY に昇格（1件ずつ確認）
python scripts/approve_queue.py --account-id night_scout --queue-id {id}

# rights確認
python scripts/review_queue.py --account-id night_scout --rights-review-required true
```

## 5. Learning Export/Import

```bash
# 改善提案のエクスポート
python scripts/export_learning_context.py --account-id night_scout --dry-run

# 改善提案のインポート
python scripts/import_improvement_suggestions.py --dry-run

# 学習ルールの確認
python scripts/check_learning_integrity.py --account-id night_scout
```

## 6. Weekly Report

```bash
# 週次レポート生成（dry-run）
python scripts/generate_weekly_growth_report.py --account-id night_scout --dry-run
```

## 7. X投稿前チェック

```bash
# 投稿前preflight（実投稿なし・常時安全）
python scripts/preflight_x_real_post.py --account-id night_scout

# smoke test plan確認
python scripts/run_real_smoke_plan.py --step x --account-id night_scout
```

実投稿手順 → `docs/x-real-post-final-checklist.md`

## 8. Cloudflare / Cloudinary Smoke Test

```bash
# 準備状況確認
python scripts/run_real_smoke_plan.py --step cloudflare
python scripts/run_real_smoke_plan.py --step cloudinary

# 認証情報確認
python scripts/test_cloudflare_transcription_credentials.py
python scripts/test_cloudinary_credentials.py
```

実テスト手順:
- Cloudflare → `docs/cloudflare-transcription-runbook.md`
- Cloudinary → `docs/cloudinary-upload-runbook.md`

## 9. エラー時の対応

| エラー種別 | 対応 |
|-----------|------|
| Sheets接続エラー | `python scripts/preflight_check.py --skip-gemini` で確認 |
| Gemini API エラー | `GEMINI_API_KEY` 確認、モデル名確認 |
| queue整合性エラー | `python scripts/check_pipeline_integrity.py --mock` で確認 |
| learning整合性エラー | `python scripts/check_learning_integrity.py --mock` で確認 |
| 誤投稿・誤実行 | `docs/emergency-rollback.md` 参照 |

## 緊急対応

→ `docs/emergency-rollback.md` 参照

## 10. thread_series 生成（Phase 6.2）

```bash
# dry-run 生成（night_scout）
python scripts/generate_thread_series.py \
  --account-id night_scout --platform x \
  --theme "夜職で月50万稼ぐ方法" --mock-llm

# beauty_account（draft_only 確認・WAITING_REVIEW のみ）
python scripts/generate_thread_series.py \
  --account-id beauty_account --platform threads --post-count 5 --mock-llm

# レビュー
python scripts/review_thread_series.py --account-id beauty_account

# パイプライン integrity チェック（account_config 安全確認込み）
python scripts/check_pipeline_integrity.py --mock
```

## 11. account_config 管理（Phase 6.0）

```bash
# 新規アカウント追加
cp config/account_templates/base_account.json config/accounts/new_account.json
# → 編集後、test_account_config_loader.py で確認

# beauty_account は draft_only のまま運用
# READY 化・実投稿は禁止。ユーザー明示承認が必要。
```

## 重要チェックリスト

毎回作業前に確認:
- [ ] 作業ディレクトリが `v2` であること
- [ ] `PUBLISH_ENABLED=false` であること
- [ ] `ALLOW_REAL_X_POST=false` であること
- [ ] git status がクリーンであること
- [ ] beauty_account は status=draft_only のまま（READY 化禁止）


---

## Phase 8 追加: Source Registry 運用

### source account確認
```bash
python3 scripts/manage_source_accounts.py --list --dry-run
python3 scripts/manage_source_accounts.py --account-id night_scout --active-only --validate --dry-run
```

### source collection plan確認
```bash
python3 scripts/plan_source_collection.py --account-id night_scout --source-platform x --top-n 5 --dry-run --mock
```

### source rights確認ルール
- rights_policy=unknown → WAITING_REVIEW（手動確認必須）
- media_policy=do_not_download → download禁止
- media_policy=plan_only → planのみ、upload不可
- source priority変更 → 改善提案のみ、自動変更禁止

### beauty_account活性化確認
```bash
python3 scripts/check_beauty_activation_readiness.py --mock
```
現時点では常にBLOCKED/NOT_READY。

### 実LLM生成前確認
```bash
python3 scripts/preflight_real_llm_generation.py --account-id night_scout --platform x --mock
```

---

## Phase 9-12 追加 CLI（2026-06-15 更新）

### Fetcher ツール確認
```bash
python3 scripts/check_source_fetcher_tools.py
```
yt-dlp / ffmpeg / youtube-transcript-api の導入状況を確認します。

### ソース候補 dry-run fetch
```bash
python3 scripts/fetch_sources.py --source-id src_ns_yt_001 --dry-run
python3 scripts/fetch_sources.py --source-id src_ns_yt_001 --confirm-fetch
```

### SourceToPostOrchestrator dry-run
```bash
python3 scripts/run_source_to_post.py --account-id night_scout --platform threads --dry-run
```

### パイプライン出力保存
```bash
python3 scripts/save_pipeline_outputs.py --run-id RUN_XXXX --dry-run
```

### ソース候補管理
```bash
python3 scripts/add_source_candidate.py --source-id src_ns_yt_001 --status candidate
python3 scripts/review_source_candidates.py --account-id night_scout
python3 scripts/update_source_status.py --source-id src_ns_yt_001 --status approved
```

### 安全確認チェックリスト（Phase 13 以降）
- `confirm_fetch` なしで実 fetch しない
- `confirm_download` なしで動画 DL しない
- `confirm_cut` なしで ffmpeg カットしない
- `confirm_upload` なしで Cloudinary upload しない
- `confirm_post` なしで実投稿しない
- `beauty_account` は常に draft_only（active 化禁止）
