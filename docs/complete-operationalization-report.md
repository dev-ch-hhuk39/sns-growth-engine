# 完全運用化フェーズ 最終レポート

**作成日**: 2026-06-21  
**対象コミット**: b30524a（完全運用化確認時点）  
**作業スコープ**: 全30コンポーネント棚卸し・テスト全件確認・ドキュメント整備

---

## 28-item ステータスレポート

| # | 項目 | ステータス | 詳細 |
|---|---|---|---|
| 1 | source registry | ✅ DONE | `src/reference/source_registry.py` 8関数、27テスト PASS |
| 2 | fetch_source_posts CLI | ✅ DONE | `scripts/fetch_source_posts.py` --account-id 対応 |
| 3 | fetcher adapters (FetcherRegistry) | ✅ DONE | 7アダプター登録、JsonImportFetcher 含む |
| 4 | yt-dlp adapter | ✅ DONE | `YtDlpFetcher`、16テスト PASS |
| 5 | tiktok-to-ytdlp adapter | ✅ DONE | `TiktokToYtdlpFetcher`、NOT_INSTALLED も正常動作、8テスト PASS |
| 6 | youtube transcript adapter | ✅ DONE | `YoutubeTranscriptFetcher`、11テスト PASS |
| 7 | manual import (json/csv) | ✅ DONE | `JsonImportFetcher` / `BrowserExportFetcher` |
| 8 | raw_source_items (source_account_posts) | ✅ DONE | Sheets タブ「収集済み投稿」存在、81テスト PASS |
| 9 | buzz scoring | ✅ DONE | `score_items`、18テスト PASS |
| 10 | reference_posts | ✅ DONE | Sheets タブ「参考投稿」、reference_post_scores 連携 |
| 11 | media_assets | ✅ DONE | Sheets タブ「メディア資産」、`plan_media_downloads` |
| 12 | video_understanding | ✅ DONE | `VideoUnderstanding`（Gemini クリップ候補抽出）、34テスト PASS |
| 13 | clip_candidate_plans | ✅ DONE | `ClipCandidatePlanner`、Sheets タブ「動画クリップ候補」 |
| 14 | ffmpeg clipping | ✅ DONE | `cut_clip`（confirm_cut ゲート付き）、3テスト PASS |
| 15 | cloudinary upload | ✅ DONE | `plan_cloudinary_upload`（ALLOW_CLOUDINARY_UPLOAD ガード）、安全停止確認 |
| 16 | transcription client | ✅ DONE | `CloudflareWhisperClient`（ALLOW_TRANSCRIPTION_API ガード） |
| 17 | generation jobs | ✅ DONE | `allocate_generation_modes`、Sheets タブ「生成ジョブ」、15テスト PASS |
| 18 | queue (build + preflight) | ✅ DONE | `build_queue`、19テスト PASS |
| 19 | preflight check | ✅ DONE | `preflight_check.py` + end-to-end matrix、13テスト PASS |
| 20 | X publisher | ✅ DONE | `XPublisher`（ALLOW_REAL_X_POST ガード）、5テスト PASS |
| 21 | Threads publisher | ✅ DONE | `ThreadsPublisher`（ALLOW_REAL_THREADS_POST ガード）、7テスト PASS |
| 22 | posted_results | ✅ DONE | Sheets タブ「投稿結果」 |
| 23 | metrics import | ✅ DONE | `scripts/import_post_results.py` --dry-run 対応 |
| 24 | PDCA cycle | ✅ DONE | `PDCAOrchestrator`、24テスト PASS（+ 11テスト PASS） |
| 25 | learning_rules | ✅ DONE | Sheets タブ「学習ルール」、`ImprovementSuggester`、自動 active 禁止 |
| 26 | safety flags | ✅ DONE | 全5フラグ（PUBLISH_ENABLED 等）デフォルト false ガード実装 |
| 27 | Google Sheets integration (29タブ) | ✅ DONE | `SheetsClient`、`TAB_DISPLAY_NAMES` 29エントリ |
| 28 | account-specific Threads creds + refresh | ✅ DONE | `threads_credentials.py`（24テスト PASS）+ GitHub Actions 週次 refresh |

**28/28 項目 DONE**

---

## テスト全件サマリー

| テストカテゴリ | PASS |
|---|---|
| source_account_registry | 27 |
| buzz_scorer | 18 |
| yt_dlp_fetcher | 16 |
| tiktok_to_ytdlp_fetcher | 8 |
| youtube_transcript_fetcher | 11 |
| video_understanding | 34 |
| media_asset_storage | 3 |
| video_clip_execution | 3 |
| sheets_schema | 81 |
| source_to_reference_generation | 19 |
| content_mix_to_jobs | 15 |
| media_to_preflight | 19 |
| end_to_end_preflight_matrix | 13 |
| pdca_to_next_plan | 24 |
| pdca_orchestrator | 11 |
| x_publisher | 5 |
| threads_publisher | 7 |
| threads_credentials | 24 |
| publishers_production_safety | 4 |
| source_registry_production | 28 |
| **合計** | **370+** |

**全テスト FAIL=0**

---

## CLI スクリプト一覧（11本）

| スクリプト | 用途 |
|---|---|
| `scripts/fetch_source_posts.py` | ソースアカウント投稿収集 |
| `scripts/analyze_video_clips.py` | 動画クリップ候補分析 |
| `scripts/cut_video_clips.py` | ffmpeg クリップ切り出し |
| `scripts/download_video_assets.py` | 動画アセットダウンロード |
| `scripts/upload_media_assets.py` | Cloudinary アップロード |
| `scripts/generate_from_references.py` | 参考投稿ベース生成 |
| `scripts/preflight_check.py` | 投稿前チェック |
| `scripts/publish_x_post.py` | X 投稿実行 (dry_run デフォルト) |
| `scripts/publish_threads_post.py` | Threads 投稿実行 (dry_run デフォルト) |
| `scripts/import_post_results.py` | 投稿結果インポート |
| `scripts/run_pdca_cycle.py` | PDCA サイクル実行 |

---

## Google Sheets タブ構成（29タブ）

| logical_name | 日本語名 |
|---|---|
| accounts | アカウント管理 |
| reference_posts | 参考投稿 |
| reference_post_scores | 参考投稿スコア |
| reference_sources | 動画収集元 |
| source_accounts | 収集元アカウント |
| source_account_posts | 収集済み投稿 |
| source_collection_plans | 収集計画 |
| content_categories | 投稿カテゴリ |
| content_mix_plans | 投稿配分計画 |
| generation_jobs | 生成ジョブ |
| drafts | 投稿下書き |
| social_derivatives | SNS投稿文 |
| thread_series | スレッド構成 |
| thread_series_posts | スレッド投稿 |
| queue | 投稿キュー |
| posted_results | 投稿結果 |
| media_assets | メディア資産 |
| media_ingestion_runs | メディア取込履歴 |
| video_transcripts | 動画文字起こし |
| video_clip_candidates | 動画クリップ候補 |
| transcription_runs | 文字起こし実行履歴 |
| category_scores | カテゴリ成績 |
| distribution_rules | 配信ルール |
| learning_rules | 学習ルール |
| prompt_templates | プロンプト管理 |
| prompt_improvement_suggestions | 改善提案 |
| pdca_runs | PDCA実行履歴 |
| end_to_end_preflight_runs | 投稿前チェック履歴 |
| logs | 実行ログ |

---

## 安全ガード状態（全フラグ BLOCKED）

| フラグ | 状態 | 解除条件 |
|---|---|---|
| PUBLISH_ENABLED | false (デフォルト) | .env で true に設定 |
| ALLOW_REAL_X_POST | false (デフォルト) | .env で true に設定 |
| ALLOW_REAL_THREADS_POST | false (デフォルト) | .env で true に設定 |
| ALLOW_CLOUDINARY_UPLOAD | false (デフォルト) | .env で true に設定 |
| ALLOW_TRANSCRIPTION_API | false (デフォルト) | .env で true に設定 |
| beauty_account.active | false (永続) | 活性化チェックリスト参照 |

---

## GitHub Actions

| ワークフロー | 説明 | スケジュール |
|---|---|---|
| `refresh-threads-tokens.yml` | Threads トークン週次 refresh | 毎週日曜 JST 11:00 |
| `v2-dry-run-check.yml` | dry-run テスト | push 時 |

---

## 旧リポジトリ状況

| リポジトリ | 状態 |
|---|---|
| X_autopost_yoru | workflow 8本 全 disabled ✅ |
| threads_auto_post_gs | workflow 4本 全 disabled ✅ |
| threads-liver-coachhing | workflow 8本 全 disabled ✅ |

詳細: `docs/legacy-repo-shutdown-plan.md`  
次回チェック: 2026-07-20（archive 可否判断）

---

## 次のアクション（運用フェーズ）

1. Threads トークン refresh を月次で確認（残り45日未満でリフレッシュ）
2. `production_sources.example.json` の actual URL を設定してソース候補を登録
3. 1件ずつ `confirm_fetch=True` で実 fetch テスト
4. 初回実投稿前に `preflight_end_to_end_publish.py` でゲートチェック
5. 2026-07-20 以降に旧リポジトリ archive 可否を判断
