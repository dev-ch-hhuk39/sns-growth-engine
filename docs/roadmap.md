# sns-growth-engine 実装ロードマップ

**最終更新**: 2026-05-30

---

## フェーズ概要

```
[完了] Phase 1〜3-D  → 投稿実行エンジン（安全ガード付き）
[完了] Phase 0       → Git/GitHub保全
[完了] Phase 2.8     → reference pipeline 設計・スタブ・スキーマ追加
[完了] Phase 2.9     → 実Sheetsに新タブ（media_assets / reference_post_scores / generation_jobs）反映
[完了] Phase 2.10    → X reference collector 移植（JSON/mock入力対応、X API本番未実行）
[次期] Phase 2.11    → reference_post_analyzer 移植
[中期] Phase 2.12    → Cloudinary media_assets 統合
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

## Phase 2.11: X analyzer 移植

**目的**: 分析・スコアリング・Geminiリライト提案をv2に移植する

- [ ] `x_analyze_posts.py` → v2 `src/analyzers/x_analyzer.py` として移植
- [ ] パフォーマンス計算式の移植
  - `performance_score = like + (repost×3) + (reply×2) + (bookmark×4) + (impression/100)`
- [ ] content_angle / hook_style 分類の移植
- [ ] バズ判定ロジックの移植
- [ ] Geminiリライト提案（rewrite_light / rewrite_reframe）の移植
- [ ] `x_sync_post_queue.py` → v2 queue 同期フローに統合
- [ ] テスト追加

---

## Phase 2.12: Cloudinary media_assets 統合

**目的**: 画像・動画のアップロード・管理をCloudinaryで一元化する

- [ ] Cloudinaryアカウント・APIキー設定
- [ ] `src/media/cloudinary_uploader.py` 実装
- [ ] `x_prepare_media_assets.py` 相当の実装
- [ ] v2 スプシスキーマへのメディアURL管理カラム追加
- [ ] テスト追加

---

## Phase 2.13: 8:2 generation planner

**目的**: 80% reference_based / 20% original_hypothesis の投稿比率を管理する

- [ ] 投稿比率カウンタの設計
- [ ] `src/planners/generation_planner.py` 実装
- [ ] 週次・月次の比率モニタリング
- [ ] テスト追加

---

## Phase 2.14: reference_based Gemini prompt

**目的**: 収集投稿をベースにしたリライト用Geminiプロンプトをv2に統合する

- [ ] `prompts/rewrite_reference.md` 作成
- [ ] reference_based 生成フローの実装
- [ ] 既存 `x_analyze_posts.py` のリライトロジックとの統合
- [ ] テスト追加

---

## Phase 2.15: AI approval scoring

**目的**: 投稿案に対してAIがスコアリングし人間レビューを支援する

- [ ] `src/scorers/approval_scorer.py` 実装
- [ ] スコア基準の定義（バズ可能性・ブランド整合性・文字数 等）
- [ ] `approve_queue.py` への統合
- [ ] テスト追加

---

## Phase 2.16: 文字数制限強化

**目的**: 全プラットフォームの文字数制限をコード・プロンプト双方で徹底する

- [ ] X: 120文字推奨 / 140文字ハード上限（v2 XPublisher は実装済み）
- [ ] Threads: 500文字上限
- [ ] Geminiプロンプトへの文字数制約追加（`collect.py` 相当）
- [ ] `generate_drafts.py` での事後検証
- [ ] テスト追加

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
