# Google Sheets スキーマ定義

`src/sheets_client.py` の `TAB_DEFINITIONS` で管理するタブ一覧。

## Phase別タブ追加履歴

| Phase | タブ名 | 概要 |
|---|---|---|
| 1-2 | accounts, reference_posts, drafts, queue, logs, posted_results, ... | 基本スキーマ |
| 2.8 | media_assets, reference_post_scores, reference_sources | メディア・参考 |
| 2.18 | video_transcripts, video_clip_candidates, transcription_runs | 動画パイプライン |
| 2.13 | generation_jobs | 生成ジョブ |
| 4.0 | prompt_improvement_suggestions | 学習・改善提案 |
| 6 | thread_series, thread_series_posts | ツリー投稿 |
| 8 | content_mix_plans, source_accounts, source_account_posts, source_collection_plans, media_ingestion_runs, end_to_end_preflight_runs, pdca_runs | Phase 8追加 |

## Phase 8 追加タブ

### content_mix_plans
content_mix_plannerの計画記録。

主要列: `plan_id, account_id, platform, content_type, status, seed, force_mode, planned_at`

### source_accounts
source account registryの設定管理。実データではなく設定情報。

主要列: `source_id, source_name, source_platform, source_handle, source_url, target_account_ids, collection_method, active, blocked, priority, rights_policy, reuse_policy, media_policy`

### source_account_posts
source accountから収集した投稿記録。

主要列: `post_id, source_id, account_id, source_platform, post_text, engagement_rate, buzz, rights_policy, status, collected_at`

### source_collection_plans
source collection計画記録。

主要列: `plan_id, account_id, source_id, platform, content_type, top_n, status, created_at`

### media_ingestion_runs
media ingestion実行記録。

主要列: `run_id, account_id, source_id, media_asset_id, source_url, media_type, rights_status, reuse_risk, media_policy, upload_status, plan_status, created_at`

### end_to_end_preflight_runs
end-to-end preflight実行記録。

主要列: `run_id, account_id, platform, post_type, overall_status, pass_count, fail_count, warn_count, blocked_count, created_at`

### pdca_runs
PDCA実行記録。

主要列: `run_id, account_id, platform, days, total_results, suggestion_count, next_jobs_count, best_content_type, created_at`

## セットアップ

```bash
# dry-runで差分確認
python3 scripts/setup_and_verify.py --dry-run

# セットアップ実行（Sheets API必要）
python3 scripts/setup_and_verify.py --setup

# 検証
python3 scripts/setup_and_verify.py --verify
```

## 安全ルール

- 既存タブのデータを削除しない
- 既存列を削除しない
- dry-run時は書き込みしない
- Sheets API 429 エラー時は安全に中断してリトライ
- posted_results への本番データ書き込み禁止
