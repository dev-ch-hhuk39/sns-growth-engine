# sns-growth-engine 実装ロードマップ

**最終更新**: 2026-05-31

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

## Phase 4: AI自動化・学習ループ

**目的**: 人間レビューを最小化し、投稿結果から継続改善する

- [ ] AI自動承認スコアリング（Phase 2.15の発展）
- [ ] 投稿結果の自動収集・フィードバックループ
- [ ] パフォーマンス予測モデルの構築
- [ ] 自動投稿スケジューリング（GitHub Actions CI/CD）
- [ ] ダッシュボード・パフォーマンス可視化
