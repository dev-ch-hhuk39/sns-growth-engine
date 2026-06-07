# sns-growth-engine 実装ロードマップ

**最終更新**: 2026-06-06 (Phase 2.25〜2.28追加)

---

## フェーズ概要

```
[完了] Phase 1〜3-D  → 投稿実行エンジン（安全ガード付き）
[完了] Phase 0       → Git/GitHub保全
[完了] Phase 2.8     → reference pipeline 設計・スタブ・スキーマ追加
[完了] Phase 2.9     → 実Sheetsに新タブ（media_assets / reference_post_scores / generation_jobs）反映
[完了] Phase 2.10    → X reference collector 移植（JSON/mock入力対応、X API本番未実行）
[完了] Phase 2.11    → reference_post_analyzer 移植（スコアリング・分類・パーセンタイル）
[完了] Phase 2.12    → Cloudinary media_assets 統合
[完了] Phase 2.13    → 8:2 generation planner
[完了] Phase 2.14    → reference_based Gemini prompt（リライトループ）
[完了] Phase 2.15    → AI approval scoring
[完了] Phase 2.16    → 文字数制限強化（X 120/140字）
[完了] Phase 2.17    → アカウント別コンテンツテーマガード（禁止キーワード検出・READY拒否）
[完了] Phase 2.18    → 動画 reference スキーマ拡張（4新タブ + reference_posts 列追加）
[完了] Phase 2.19    → 動画収集アダプター基盤（YouTube/TikTok コレクター・mock対応）
[完了] Phase 2.20    → Cloudflare Whisper 文字起こし基盤（日次120分制限・安全ガード）
[完了] Phase 2.21    → clip_candidate_analyzer（Gemini でクリップ候補抽出・mock対応）
[完了] Phase 2.22    → ffmpeg clip cutter 基盤（dry-run デフォルト・安全ガード）
[完了] Phase 2.23    → media_assets / drafts / social_derivatives / queue スキーマ拡張
[完了] Phase 2.24    → clip-based 投稿文生成（権利ゲート・WAITING_REVIEW キュー）
[完了] Phase 2.25    → 動画パイプライン統合実行 CLI (run_video_pipeline.py)
[完了] Phase 2.26    → 動画ダウンロード・音声抽出基盤 (yt-dlp / ffmpeg)
[完了] Phase 2.27    → Cloudflare 文字起こし認証情報・スモークテスト CLI
[完了] Phase 2.28    → 権利レビューワークフロー改訂（unknown→WAITING_REVIEW）
[長期] Phase 4       → AI自動化・学習ループ
```

---

## Phase 0: GitHub repository 作成（現在）

**目的**: v2コードをGitHubに安全に保全する

- [ ] v2 `git init`
- [ ] `.gitignore` 作成（秘密情報の除外確認）
- [ ] `README.md` 作成
- [ ] `docs/` 棚卸しドキュメント作成
- [ ] 秘密情報チェック（`.env` / GCP JSON / APIキー）
- [ ] テスト全通過確認（150 PASS / 0 FAIL）
- [ ] 初回コミット
- [ ] GitHub private repo 作成（`sns-growth-engine`）
- [ ] push

---

## Phase 2.8: 既存Xパイプライン棚卸しdocs化 ✅

**目的**: `feature/x-analysis-pipeline` の設計・仕様をv2 docsに記録する

- [x] 監査レポート作成（`docs/phase2-8-existing-x-pipeline-audit.md`）
- [x] スキーマ対応表作成（`docs/schema-mapping-existing-x-to-v2.md`）
- [x] 統合計画作成（`docs/v2-x-pipeline-integration-plan.md`）
- [x] TAB_DEFINITIONS に media_assets / reference_post_scores / generation_jobs 追加
- [x] src/collectors / analyzers / media / generation スタブ作成
- [x] text_policy.py 実装（X: 120/140字、Threads: 600/800字）
- [x] generation_planner.py 最小実装
- [x] test_phase28.py 51 PASS

---

## Phase 2.9: 実Sheets スキーマ有効化 ✅

**目的**: v2のスプシスキーマを実Sheetsに反映する

- [x] `setup_and_verify.py --setup --verify` 実行
- [x] media_assets タブ作成
- [x] reference_post_scores タブ作成
- [x] generation_jobs タブ作成
- [x] reference_posts に6列追加（Phase 2.10用）
- [x] 既存タブのデータ破壊なし確認

---

## Phase 2.10: X reference collector 移植 ✅

**目的**: X投稿収集パイプラインをv2に移植する（X API本番未実行）

- [x] `src/collectors/x_reference_collector.py` 本格実装（normalize_post）
- [x] JSON / mock 入力対応
- [x] X API クライアントスタブ（--use-x-api フラグで有効化設計）
- [x] `scripts/collect_references.py` CLI作成
- [x] `fixtures/sample_x_posts.json` 作成（3件: テキスト/画像/動画）
- [x] `SheetsClient.save_reference_post()` / `save_reference_posts()` 追加
- [x] `MockSheetsClient` に同じメソッド追加
- [x] check_pipeline_integrity.py に新タブチェック追加
- [x] test_phase29_210.py 67 PASS

---

## Phase 2.11: reference_post_analyzer 移植 ✅

**目的**: 分析・スコアリング・パーセンタイル計算をv2に移植する

- [x] `src/analyzers/reference_post_analyzer.py` 本実装
  - `performance_score = likes + reposts×3 + reply_count×2 + bookmark_count×4 + impressions/100`
  - `buzz_score = min(100.0, performance_score / 500 × 100)`
- [x] content_angle / hook_style 分類の移植
- [x] pure Python percentile_rank（pandas不使用）
- [x] `analyze_reference_post()` / `analyze_reference_posts()` 実装
  - バッチ処理で account_percentile / keyword_percentile を更新
- [x] `why_it_grew()` / `replay_tip()` 実装
- [x] `SheetsClient` / `MockSheetsClient` に reference_post_scores 4メソッド追加
  - `get_reference_post_scores` / `find_reference_post_score_by_reference_post_id`
  - `save_reference_post_score`（reference_post_id でアップサート）
  - `save_reference_post_scores`
- [x] `scripts/analyze_references.py` CLI 作成
- [x] `check_pipeline_integrity.py` reference_post_scores チェック強化
- [x] `fixtures/sample_x_posts.json` 3件 → 6件に拡張
- [x] `test_phase211.py` 117 PASS

---

## Phase 2.12: Cloudinary media_assets 統合 ✅

**目的**: 画像・動画のアップロード・管理をCloudinaryで一元化する基盤を構築する

- [x] `docs/phase2-12-cloudinary-media-assets.md` 作成
- [x] `docs/media-assets-schema.md` 作成
- [x] `docs/media-reuse-risk-policy.md` 作成
- [x] `.env.template` に Cloudinary 設定変数追加（ALLOW_CLOUDINARY_UPLOAD=false）
- [x] `src/config_loader.py` に `get_cloudinary_config()` 追加
- [x] `src/media/cloudinary_client.py` 本実装（dry_run=True デフォルト、2重ガード）
- [x] `SheetsClient` / `MockSheetsClient` に media_assets 5メソッド追加
- [x] `scripts/prepare_media_assets.py` CLI 作成
- [x] `scripts/check_pipeline_integrity.py` media_assets チェック強化
- [x] `fixtures/sample_media_assets.json` 追加
- [x] `scripts/test_phase212.py` 作成

---

## Phase 2.13: 8:2 generation planner ✅

**目的**: 80% reference_based / 20% original_hypothesis の投稿比率を管理する

- [x] `src/generation/generation_planner.py` 実装
  - `plan_daily_counts()` / `allocate_generation_modes()` / `select_reference_candidates()`
  - `build_generation_job()` / `build_generation_job_records()` / `plan_generation_jobs()`
  - `create_generation_jobs_for_account()` / `create_daily_generation_plan()`
- [x] `SheetsClient` / `MockSheetsClient` に generation_jobs 5メソッド追加
  - `save_generation_job` / `save_generation_jobs` / `get_generation_jobs`
  - `find_generation_job_by_id` / `update_generation_job`
- [x] TAB_DEFINITIONS generation_jobs に status / generated_draft_id / generated_at 追加
- [x] `scripts/plan_generation_jobs.py` CLI 作成
- [x] `fixtures/sample_generation_jobs.json` 追加（3件）
- [x] `check_pipeline_integrity.py` generation_jobs バリデーション強化
- [x] `test_phase213_216.py` 123 PASS

---

## Phase 2.14: reference_based Gemini prompt ✅

**目的**: 収集投稿をベースにしたリライト用Geminiプロンプトをv2に統合する

- [x] `src/generation/reference_based_generator.py` 実装
  - `build_reference_based_prompt()` / `build_original_hypothesis_prompt()`
  - `parse_generation_response()` / `_call_with_rewrite()`（2回リトライループ）
  - `generate_from_reference()` / `generate_original_hypothesis()`
  - `normalize_generated_draft()` / `execute_generation_job()` / `execute_generation_jobs()`
- [x] MOCK_LLM=true デフォルト（実Gemini API 未呼び出し）
- [x] text_policy FAIL → WAITING_REVIEW 自動マッピング
- [x] `scripts/generate_from_jobs.py` CLI 作成（--mock-llm / --dry-run デフォルト）
- [x] `fixtures/sample_generated_posts.json` 追加（2件）
- [x] `docs/phase2-14-reference-based-generator.md` 作成
- [x] `docs/reference-based-prompt-design.md` 作成
- [x] `test_phase213_216.py` 内 generation テスト PASS

---

## Phase 2.15: AI approval scoring ✅

**目的**: 投稿案に対してAIがスコアリングし人間レビューを支援する

- [x] `src/generation/approval_scorer.py` 実装
  - `calculate_buzz_potential_score()` / `calculate_conversion_potential_score()`
  - `calculate_brand_risk_score()` / `calculate_imitation_risk()` / `calculate_media_reuse_risk()`
  - `calculate_confidence_level()` / `should_auto_approve()` / `calculate_ai_publish_recommendation()`
  - `score_generated_post()` / `_text_overlap_ratio()`
- [x] TAB_DEFINITIONS drafts に buzz_potential_score / conversion_potential_score /
      confidence_level / ai_publish_recommendation 等追加
- [x] `docs/phase2-15-ai-approval-scoring.md` 作成
- [x] `docs/ai-approval-policy.md` 作成
- [x] `test_phase213_216.py` 内 approval scoring テスト PASS

---

## Phase 2.16: 文字数制限強化 ✅

**目的**: 全プラットフォームの文字数制限をコード・プロンプト双方で徹底する

- [x] X: 120文字推奨 / 140文字ハード上限（soft/hard 2段階）
- [x] Threads: 500文字推奨 / 800文字ハード上限
- [x] Geminiプロンプト内に文字数制約を明示（reference_based / original_hypothesis 両プロンプト）
- [x] `_call_with_rewrite()` でリライトループ（FAIL → 再生成、最大2回）
- [x] `normalize_generated_draft()` で text_policy_status=FAIL → status=WAITING_REVIEW
- [x] TAB_DEFINITIONS social_derivatives に char_count / text_policy_status 追加
- [x] `docs/phase2-16-text-policy-enforcement.md` 作成
- [x] `docs/8-2-generation-strategy.md` 作成
- [x] `test_phase213_216.py` 内 text_policy 統合テスト PASS

---

## Phase 2.17: アカウント別コンテンツテーマガード ✅

**目的**: ターゲット外コンテンツ（代理店・B2B向け）の生成・キュー登録を防止する

- [x] Sheetsデータ修正（代理店向け投稿をREJECTED、ns_08/lm_08 inactive化）
- [x] `src/seeds.py` — `ACCOUNT_FORBIDDEN_KEYWORDS` / `ACCOUNT_FORBIDDEN_THEMES` 追加、ns_08/lm_08 inactive、プロンプトNG追記
- [x] `src/generation/reference_based_generator.py` — `_get_account_ng_block()` でプロンプトにNG注入
- [x] `src/generation/approval_scorer.py` — `detect_forbidden_keywords` / `check_content_theme` / `calculate_target_fit_score` / `apply_content_theme_guard` 追加
- [x] `scripts/generate_from_jobs.py` — 生成後テーマチェック（ヒット→WAITING_REVIEW）
- [x] `scripts/approve_queue.py` — READY昇格前ゲート（ヒット→拒否）
- [x] `scripts/check_pipeline_integrity.py` — REJECTED追加 + `check_content_theme_in_queue` [WARN]
- [x] `docs/phase2-17-content-theme-guard.md` 作成
- [x] `docs/account-targeting-policy.md` 作成
- [x] `docs/ai-approval-policy.md` 更新
- [x] `scripts/test_phase217.py` 作成

---

## Phase 2.18: 動画 reference スキーマ拡張 ✅

**目的**: YouTube/TikTok 動画を参考投稿として取り込む基盤スキーマを構築する

- [x] `reference_sources` タブ追加（source_id / account_id / platform / handle / priority / active 等）
- [x] `video_transcripts` タブ追加（transcript_id / reference_post_id / transcription_status / segments_json 等）
- [x] `video_clip_candidates` タブ追加（clip_id / start_time / end_time / hook / rights_status 等）
- [x] `transcription_runs` タブ追加（run_id / date / used_minutes / remaining_minutes 等）
- [x] `reference_posts` に 14 列追加（content_type / video_id / creator_handle / duration_seconds / transcription_status 等）
- [x] SheetsClient に 4 タブ × 4〜5 メソッド追加
- [x] MockSheetsClient に同メソッド追加
- [x] `docs/phase2-18-video-reference-schema.md` 作成

---

## Phase 2.19: 動画収集アダプター基盤 ✅

**目的**: YouTube/TikTok 動画メタデータを mock/JSON で収集・正規化する基盤を構築する

- [x] `src/collectors/video_source_manager.py` 実装（ソース登録・取得・mark_collected）
- [x] `src/collectors/youtube_video_collector.py` 実装（normalize_youtube_video / collect_from_mock / collect_from_json_file）
- [x] `src/collectors/tiktok_video_collector.py` 実装（normalize_tiktok_video / collect_from_mock / collect_from_json_file）
- [x] `fixtures/sample_video_references.json` 作成（YouTube 3件 / TikTok 2件）
- [x] `docs/phase2-19-video-source-collectors.md` 作成

---

## Phase 2.20: Cloudflare Whisper 文字起こし基盤 ✅

**目的**: Cloudflare Workers AI Whisper を使った文字起こし基盤（日次120分制限・安全ガード付き）

- [x] `.env.template` に CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN / ALLOW_TRANSCRIPTION_API=false 追加
- [x] `src/config_loader.py` に `get_transcription_config()` 追加
- [x] `src/transcription/__init__.py` 作成
- [x] `src/transcription/cloudflare_whisper_client.py` 実装（2重安全ガード・dry_run・mock対応）
- [x] `src/transcription/transcription_limiter.py` 実装（初期化from Sheets・インメモリ累積・flush）
- [x] `src/transcription/transcript_parser.py` 実装（parse_segments / extract_clip_window / build_clip_candidate）
- [x] `scripts/transcribe_videos.py` CLI 作成（dry_run デフォルト・--allow-real-transcription フラグ）
- [x] `fixtures/sample_cloudflare_whisper_response.json` 作成
- [x] `fixtures/sample_transcript_segments.json` 作成
- [x] `docs/phase2-20-cloudflare-whisper-transcription.md` 作成
- [x] `docs/video-reference-pipeline.md` 作成
- [x] `docs/transcription-cost-control.md` 作成
- [x] `scripts/test_phase218_220.py` 作成

---

## Phase 2.21: clip_candidate_analyzer ✅

**目的**: 動画文字起こしから SNS 転用クリップ候補を Gemini で自動抽出する

- [x] `src/video/__init__.py` 作成
- [x] `src/video/clip_candidate_analyzer.py` 実装
  - `analyze_transcript()` / `analyze_transcripts_batch()`
  - `_normalize_candidate()` / `save_clip_candidates()`
  - mock_llm=True デフォルト（実Gemini API 未呼び出し）
- [x] `scripts/analyze_video_clips.py` CLI 作成（--use-sheets / --test-write / --mock-llm）
- [x] `tests/fixtures/sample_video_transcript.json` 作成（10分動画・9セグメント）
- [x] `tests/fixtures/sample_video_clip_candidates.json` 作成（6件・権利リスクのバリエーション付き）

---

## Phase 2.22: ffmpeg clip cutter 基盤 ✅

**目的**: ffmpeg によるクリップ切り抜き基盤を構築する（dry-run デフォルト）

- [x] `src/video/clip_cutter.py` 実装
  - `cut_clip()` / `cut_clips_batch()` / `update_cut_status()`
  - `_parse_time_to_seconds()` / `_build_output_path()`
  - 実切り抜きは `--cut --confirm-cut` 両方必要
  - ffmpeg 未インストール時は try/except でエラー返却
- [x] `scripts/cut_video_clips.py` CLI 作成
- [x] `.gitignore` に `clips/` 追加

---

## Phase 2.23: スキーマ拡張（media_assets / drafts / social_derivatives / queue） ✅

**目的**: クリップパイプラインに必要な列を既存タブに追加する

- [x] `media_assets`: video_clip_id / local_path / rights_status / permission_status / aspect_ratio / duration_seconds
- [x] `drafts`: media_asset_id / video_clip_id / source_video_url / source_time_range
- [x] `social_derivatives`: video_clip_id / source_time_range
- [x] `queue`: video_clip_id / rights_status / permission_status
- [x] `video_clip_candidates`: confidence_score / cut_status / local_clip_path / clip_media_asset_id / text_generation_status / generated_draft_id / generated_at
- [x] `_ensure_tab()` にワークシート自動リサイズ処理追加（グリッド上限超過対応）
- [x] `check_pipeline_integrity.py` に `check_video_clip_candidates()` / `check_video_transcripts()` 追加

---

## Phase 2.24: clip-based 投稿文生成 ✅

**目的**: クリップ候補から X/Threads 投稿文を生成して WAITING_REVIEW キューに追加する

- [x] `src/generation/video_clip_generator.py` 実装
  - `_is_rights_blocked()`: rights_status=unknown/not_allowed または media_reuse_risk=high → ブロック
  - `generate_from_clip()` / `save_clip_generation_result()` / `generate_from_clips_batch()`
  - 全投稿は WAITING_REVIEW（READY 昇格は人間レビュー後のみ）
  - draft → social_derivatives → queue の順で保存
  - テキストポリシーチェック（X: 120/140, Threads: 600/800）
- [x] `scripts/generate_from_video_clips.py` CLI 作成
- [x] `tests/fixtures/sample_video_clip_generation_response.json` 作成
- [x] `scripts/transcribe_videos.py` CLI フラグ新標準対応（--use-sheets / --test-write）
- [x] `docs/video-clip-rights-policy.md` 作成
- [x] `docs/video-clip-generation-usage.md` 作成
- [x] `scripts/test_phase221_224.py` 作成（61 PASS / 0 FAIL）

---

## Phase 2.25: 動画パイプライン統合実行 CLI ✅

**目的**: 動画パイプライン全ステップを1コマンドで実行できる統合 CLI を構築する

- [x] `scripts/run_video_pipeline.py` 作成
  - 7ステップ: sources → collect → transcribe → analyze → cut → generate → integrity
  - `--steps` でステップ選択可能
  - デフォルト dry-run、`--use-sheets --test-write` で実 Sheets 書き込み
  - Step 5（cut）は常に dry-run（安全ガード）
- [x] `docs/video-pipeline-runner-usage.md` 作成

---

## Phase 2.26: 動画ダウンロード・音声抽出基盤 ✅

**目的**: yt-dlp による動画ダウンロードと ffmpeg による音声抽出の基盤を構築する

- [x] `src/video/video_downloader.py` 実装
  - `download_video()` / `download_videos_batch()`
  - 実ダウンロードは `--download --confirm-download` 両方必要
  - TikTok は WARN でスキップ
- [x] `src/video/audio_extractor.py` 実装
  - `extract_audio()` / `extract_audio_batch()`
  - 16kHz mono WAV 出力（Cloudflare Whisper 推奨フォーマット）
  - 実抽出は `--extract-audio --confirm-extract` 両方必要
- [x] `scripts/download_video_assets.py` CLI 作成
- [x] `docs/video-download-usage.md` 作成

---

## Phase 2.27: Cloudflare 文字起こし認証情報・スモークテスト CLI ✅

**目的**: Cloudflare API 疎通確認のための安全なテスト CLI を構築する

- [x] `scripts/test_cloudflare_transcription_credentials.py` 作成（env check のみ）
- [x] `scripts/test_cloudflare_transcription_smoke.py` 作成
  - `--use-api --confirm-api` + `ALLOW_TRANSCRIPTION_API=true` が全部必要
  - 30秒タイムアウト
- [x] `docs/cloudflare-transcription-setup.md` 作成
- [x] `docs/cloudflare-transcription-smoke-test.md` 作成

---

## Phase 2.28: 権利レビューワークフロー改訂 ✅

**目的**: `rights_status=unknown` のクリップを可視化し、人間レビューを促進する

- [x] `_is_rights_blocked()` 変更: `unknown` はブロックしない（`not_allowed` / `high` のみブロック）
- [x] `_needs_rights_review()` 追加: `unknown` → `rights_review_required=true` を付与
- [x] queue に `rights_review_required` / `media_reuse_risk` / `source_video_url` / `source_time_range` 列追加
- [x] `video_clip_candidates` に `rights_review_required` 列追加
- [x] `approve_queue.py`: `rights_review_required=true` のアイテムの READY 昇格をブロック
- [x] `review_queue.py`: `[RIGHTS WARNING]` 表示
- [x] `generation_mode`: `"video_clip"` → `"video_clip_reference"` に統一
- [x] `clip_cutter.py`: デフォルト `-c copy`、`--reencode` で libx264/aac
- [x] `transcribe_videos.py`: `--confirm-api` エイリアス追加
- [x] `test_phase221_224.py`: Phase 2.28 動作変更に合わせて更新（65 PASS）
- [x] `docs/rights-review-workflow.md` 作成
- [x] `docs/video-clip-rights-policy.md` 更新
- [x] `scripts/test_phase225_228.py` 作成

---

## Phase 3-D 再開: X 1件本番投稿テスト

**前提条件**:
- [ ] X Developer Portal で認証情報取得済み
- [ ] `.env` に以下を設定済み:
  - `X_API_KEY`
  - `X_API_SECRET`
  - `X_ACCESS_TOKEN`
  - `X_ACCESS_TOKEN_SECRET`
- [ ] `python3 scripts/test_x_credentials.py` PASS

**実施内容**:
- [ ] `PUBLISH_ENABLED=true` / `ALLOW_REAL_X_POST=true` を `.env` に一時設定
- [ ] `python3 scripts/publish_queue.py --confirm-real-post --queue-id {id} --max-real-posts 1` 実行
- [ ] 投稿確認後、`PUBLISH_ENABLED=false` / `ALLOW_REAL_X_POST=false` に戻す

手順詳細: `docs/phase3d-x-manual-post.md`

---

## Phase 3-E: X メディア付き投稿

**目的**: tweepy `media_upload` を使った画像・動画付き投稿

- [ ] XPublisher にメディアアップロード機能追加
- [ ] `create_tweet(media_ids=[...])` 対応
- [ ] Cloudinary URL → tweepy media_upload フロー
- [ ] テスト追加

---

## Phase 3-F: Threads 本番投稿

**目的**: ThreadsPublisher の本実装

- [ ] Threads API 認証情報取得
- [ ] `.env` に `THREADS_ACCESS_TOKEN` 設定
- [ ] `threads_publisher.py` 本実装
- [ ] `ALLOW_REAL_THREADS_POST=true` 運用フロー確認
- [ ] テスト追加

---

## Phase 2.29-2.30: 動画ダウンロード強化

**実装済み（2026-06-06）**

### Phase 2.29: TikTok dry-run planning
- [x] `_extract_tiktok_video_id()` 追加
- [x] TikTok dry-run → success=True（planning 結果を返す）
- [x] TikTok 実ダウンロード → 依然 success=False（未対応）
- [x] fixture: `sample_tiktok_download_plan.json`
- [x] テスト: `test_phase229_230.py`

### Phase 2.30: 実動画テスト前提条件チェック
- [x] `scripts/preflight_video_real_test.py`
- [x] yt-dlp / ffmpeg / 環境変数 / ディレクトリ権限チェック
- [x] 実API呼び出しなし

---

## Phase HR-1: Headroom 本導入

**設計・ドキュメント完了（2026-06-06）**

- [x] `docs/headroom-production-setup.md`（インストール手順・禁止事項）
- [x] `scripts/test_headroom_installation.py`（安全ガード確認）
- [ ] `pipx install "headroom-ai[proxy]"` 実行（手動）
- [ ] `~/.local/bin/claude-hr` / `~/.local/bin/codex-hr` 作成（手動）

---

## Phase HERMES-0: Hermes Agent 導入設計

**設計のみ完了（2026-06-06）。実インストールは HERMES-1 以降。**

- [x] `docs/hermes-agent-integration-plan.md`
- [x] `docs/self-improvement-architecture.md`
- [x] ファイルベース I/O 設計（exports/hermes/ / imports/hermes/）
- [ ] Phase HERMES-1: ファイルベース分析スクリプト実装

---

## Phase 4.0-4.1: Learning / Self-Improvement Foundation

**実装済み（2026-06-06）**

### Phase 4.0: Learning foundation
- [x] `src/learning/__init__.py`
- [x] `src/learning/performance_analyzer.py` (PerformanceAnalyzer)
- [x] `src/learning/improvement_suggester.py` (ImprovementSuggester)
- [x] `scripts/export_learning_context.py`
- [x] `scripts/import_improvement_suggestions.py`
- [x] `scripts/review_improvement_suggestions.py`
- [x] `prompt_improvement_suggestions` タブ追加（TAB_DEFINITIONS）
- [x] fixtures: sample_improvement_context / suggestions / hermes_report

### Phase 4.1: Learning safety
- [x] `scripts/approve_learning_rule.py` (--confirm-approve 必須)
- [x] `scripts/check_learning_integrity.py`
- [x] `check_pipeline_integrity.py` 拡張（learning_rules / suggestions）

---

## Phase 4 Learning 改善ループ（実装済み）

### Phase 4.0-4.1（完了）: Learning 基盤
- [x] `improvement_suggester.py`（WAITING_REVIEW で提案生成）
- [x] `approve_learning_rule.py`（--confirm-approve 必須）
- [x] `check_learning_integrity.py`

### Phase 4.2（完了）: レビュー/承認フロー強化
- [x] `review_improvement_suggestions.py` filter対応（status/risk/type）
- [x] forbidden_themes 矛盾検出
- [x] 有効ステータス整理

### Phase 4.3（完了）: Hermes向け export/import 実運用
- [x] `export_learning_context.py` 4ファイル出力
- [x] `import_improvement_suggestions.py` --from-hermes 対応

### Phase 4.4（完了）: 週次改善レポート生成
- [x] `generate_weekly_growth_report.py`（Markdown + JSON）
- [x] `src/learning/weekly_report_builder.py`

### Phase 4.5（完了）: learning_rule 反映安全化
- [x] `activate_learning_rule.py`（--confirm-activate 必須）
- [x] forbidden パターン矛盾ブロック + activation ログ

---

## Phase 2.31/2.32（完了）: 実API テスト直前準備
- [x] `test_cloudinary_credentials.py`
- [x] `test_cloudinary_upload_smoke.py`（3重ガード）

## Phase 3-E（完了）: X本番投稿前最終preflight
- [x] `preflight_x_real_post.py`
- [x] `docs/x-real-post-final-checklist.md`

---

## Phase 5（今後の計画）: AI自動化・学習ループ高度化

**目的**: 人間レビューを最小化し、投稿結果から継続改善する

- [ ] AI自動承認スコアリング高度化
- [ ] 投稿結果の自動収集・フィードバックループ
- [ ] パフォーマンス予測モデルの構築
- [ ] 自動投稿スケジューリング（GitHub Actions CI/CD）
- [ ] ダッシュボード・パフォーマンス可視化
- [ ] Hermes HERMES-2: Headroom経由 LLM分析統合
