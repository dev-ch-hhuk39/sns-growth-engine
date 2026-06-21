# Production Readiness Audit

Phase 13〜完全運用化フェーズのプロダクション準備状況の監査記録。

最終更新: 2026-06-21

## 安全ゲート状態

| ゲート | デフォルト | 実行条件 |
|---|---|---|
| `confirm_fetch` | `False` | 明示的に `True` を渡す |
| `confirm_download` | `False` | 明示的に `True` を渡す |
| `confirm_post` | `False` (dry_run) | `dry_run=False` |
| `confirm_cut` | `False` | 明示的に `True` を渡す |
| `confirm_upload` | `False` | 明示的に `True` を渡す |
| `PUBLISH_ENABLED` | `false` | 環境変数で `true` に設定 |
| `ALLOW_REAL_X_POST` | `false` | 環境変数で `true` に設定 |
| `ALLOW_REAL_THREADS_POST` | `false` | 環境変数で `true` に設定 |
| `ALLOW_CLOUDINARY_UPLOAD` | `false` | 環境変数で `true` に設定 |

**全ゲートが安全な状態（デフォルト BLOCKED）であることを確認済み。**

## コンポーネント準備状況

### Phase 9 (Fetchers) — READY

| コンポーネント | ステータス | 備考 |
|---|---|---|
| BaseFetcher / RawSourceItem | READY | 40+ フィールド dataclass |
| YtDlpFetcher | READY (mock) | yt-dlp 未導入時は NOT_INSTALLED |
| TikTokToYtDlpFetcher | READY (mock) | Cookie 必須のため実運用前に審査 |
| AgentReachFetcher | READY (mock) | requires_local_login |
| Last30DaysFetcher | READY (mock) | |
| YouTubeTranscriptFetcher | READY (mock) | youtube-transcript-api 依存 |
| BrowserExportFetcher | READY | JSON/CSV import 対応 |
| ArticleFetcher | READY (mock) | note/article 対応 |

### Phase 10 (Generators / Publishers) — READY

| コンポーネント | ステータス | 備考 |
|---|---|---|
| OriginalHypothesisGenerator | READY | LLM 依存、mock 対応 |
| ThreadsPublisher | READY (dry_run) | 実投稿は PUBLISH_ENABLED 必要 |
| XPublisher | READY (dry_run) | 実投稿は ALLOW_REAL_X_POST 必要 |

### Phase 11 (Orchestrator) — READY

| コンポーネント | ステータス | 備考 |
|---|---|---|
| SourceToPostOrchestrator | READY | 5-gate 制御済み |

### Phase 13 (Production Infrastructure) — READY

| コンポーネント | ステータス | 備考 |
|---|---|---|
| ToolDoctor | READY | NOT_INSTALLED = WARN not FAIL |
| PipelineStore | READY | dry_run=True がデフォルト |
| ArticleReferenceNormalizer | READY | |
| production_sources.example.json | READY | 54件, 全 inactive |
| add_source_candidate CLI | READY | dry_run デフォルト |
| update_source_status CLI | READY | safety gate 付き |
| review_source_candidates CLI | READY | |
| publish_threads_post CLI | READY | dry_run デフォルト |
| publish_x_post CLI | READY | dry_run デフォルト |
| run_phase13_smoke_plan | READY | mock=True, dry_run=True |

## テスト状況

| テストファイル | PASS | FAIL |
|---|---|---|
| test_phase13_tool_doctor.py | 28 | 0 |
| test_phase13_pipeline_store.py | 15 | 0 |
| test_phase13_article_fetcher.py | 21 | 0 |
| test_phase13_article_normalizer.py | 18 | 0 |
| test_phase13_production_sources.py | 28 | 0 |
| test_phase13_source_lifecycle_cli.py | 23 | 0 |
| test_phase13_smoke_plan.py | 15 | 0 |
| **合計** | **148** | **0** |

Phase 9-11 テストも全て PASS。

### 完全運用化フェーズ追加テスト (2026-06-21)

| テストファイル | PASS | FAIL |
|---|---|---|
| test_threads_credentials.py | 24 | 0 |
| test_phase10_threads_publisher.py | 7 | 0 |
| test_phase10_x_publisher.py | 5 | 0 |
| test_source_account_registry.py | 27 | 0 |
| test_phase9_buzz_scorer.py | 18 | 0 |
| test_phase9_yt_dlp_fetcher.py | 16 | 0 |
| test_phase9_tiktok_to_ytdlp_fetcher.py | 8 | 0 |
| test_phase9_youtube_transcript_fetcher.py | 11 | 0 |
| test_phase9_video_understanding.py | 34 | 0 |
| test_phase8_sheets_schema.py | 81 | 0 |
| test_phase8_content_mix_to_jobs.py | 15 | 0 |
| test_phase8_source_to_reference_generation.py | 19 | 0 |
| test_phase8_media_to_preflight.py | 19 | 0 |
| test_phase8_end_to_end_preflight_matrix.py | 13 | 0 |
| test_phase8_pdca_to_next_plan.py | 24 | 0 |
| test_pdca_orchestrator.py | 11 | 0 |
| test_phase13_media_asset_storage.py | 3 | 0 |
| test_phase13_video_clip_execution.py | 3 | 0 |
| test_phase13_publishers_production_safety.py | 4 | 0 |
| test_phase13_source_registry_production.py | 28 | 0 |
| **合計 (完全運用化フェーズ)** | **370+** | **0** |

### Threads 認証情報 + トークン自動 refresh (Phase 8-Ext, 2026-06-21)

| コンポーネント | ステータス | 備考 |
|---|---|---|
| `threads_credentials.py` | READY | account_id 別解決、値はログ非表示 |
| 優先順位 (access_token) | READY | file > env_specific > fallback |
| 優先順位 (user_id/app_id等) | READY | env_specific > file > fallback |
| `refresh_threads_token.py` | READY | --dry-run / --confirm-refresh ゲート |
| refresh-threads-tokens.yml | READY | 週次 (日曜 JST 11:00) + manual dispatch |
| GH_SECRET_WRITE_TOKEN | READY | PAT secrets:write スコープ必要 |
| night_scout トークン | SET | THREADS_ACCESS_TOKEN_NIGHT_SCOUT |
| liver_manager トークン | SET | THREADS_ACCESS_TOKEN_LIVER_MANAGER |

## beauty_account 制約

- `active=false`, `fetch_enabled=false` (全ソース)
- TikTok/X ソースは `candidate_status=disabled`
- `allow_cut=false`, `allow_upload=false` (全 beauty_account ソース)
- `female_subject_required=true` (全 beauty_account ソース)
- `beauty_medical_risk_review_required=true` (全ソース)
- publish CLI から beauty_account への投稿は BLOCKED

## 本番運用前チェックリスト

- [ ] 実ソースの URL / handle をソース JSON に設定
- [ ] 各ソースの rights_policy を確認 (unknown → cc_by / permission_granted / reference_only)
- [ ] ToolDoctor で全ツール導入確認
- [ ] review_source_candidates.py でソース一覧レビュー
- [ ] 各ソースを waiting_review → candidate に昇格
- [ ] Phase 13 全テスト FAIL=0 を再確認
- [ ] run_phase13_smoke_plan.py で dry_run PASS 確認
- [ ] 実 fetch を 1件ずつ confirm_fetch=True で確認
- [ ] PUBLISH_ENABLED / ALLOW_REAL_X_POST / ALLOW_REAL_THREADS_POST を設定して実投稿確認

## 既知の NotImplementedError

`src/reference/fetchers/` 内の各アダプターは `mock=False` の実 fetch 実装が部分的。

| アダプター | mock | 実 fetch |
|---|---|---|
| YtDlpFetcher | ✓ | 部分的 (yt-dlp subprocess) |
| TikTokToYtDlpFetcher | ✓ | Cookie 取得未実装 |
| AgentReachFetcher | ✓ | ブラウザ連携未実装 |
| Last30DaysFetcher | ✓ | API 連携未実装 |
| ArticleFetcher | ✓ | requests+BS4 実装済み |
| BrowserExportFetcher | ✓ | JSON/CSV import 実装済み |
| YouTubeTranscriptFetcher | ✓ | youtube-transcript-api 実装済み |
