# Phase 3 移行前チェックリスト

Phase 3（本番 SNS 投稿）に移行する前に、以下をすべて確認すること。
すべての項目が ✅ になるまで Phase 3 の実装を開始しない。

---

## Phase 2 完了確認

- [ ] `python scripts/test_phase2.py` が **31 PASS / 0 FAIL** で通る
- [ ] `run_pipeline.py --dry-run --mock-llm` がエラーなく完走する
- [ ] drafts / social_derivatives / queue の各タブに正しいデータが入っている

---

## Phase 2.5 完了確認

- [ ] `python scripts/test_gemini_real.py` が PASS（または SKIP）で終了する
- [ ] `python scripts/test_sheets_connection.py --dry-run` が PASS（または SKIP）で終了する
- [ ] Mode C (`--dry-run --use-sheets`) でパイプラインが動作する
- [ ] Mode D (`--use-sheets --test-write`) でテスト書き込みが成功する

---

## X API 準備

- [ ] X Developer Account（Free Tier 以上）取得済み
- [ ] X API v2 の Bearer Token / API Key / API Secret / Access Token / Access Secret 取得済み
- [ ] `.env` に X API 認証情報を追加済み
- [ ] Rate Limit 確認済み（Free: 500 投稿/月）

---

## Threads API 準備

- [ ] Meta for Developers にアプリ登録済み
- [ ] Threads API のアクセストークン取得済み
- [ ] または Playwright 環境整備済み（API fallback）
- [ ] `.env` に Threads 認証情報を追加済み

---

## スプレッドシート準備

- [ ] `accounts.auto_publish` を TRUE に更新（現在は FALSE）
- [ ] `queue` タブを目視確認し、投稿対象の行に問題がないことを確認
- [ ] `status=WAITING_REVIEW` の投稿を手動確認して承認
- [ ] `scheduled_at` が正しい日時になっていることを確認

---

## GitHub Actions 準備（自動実行時）

- [ ] GitHub Secrets に以下を設定:
  - `SNS_MASTER_SHEET_ID`
  - `SA_JSON_BASE64` または `GCP_SA_JSON`
  - `GEMINI_API_KEY`
  - X API 認証情報
  - Threads API 認証情報
- [ ] `.github/workflows/pipeline.yml` 作成済み
- [ ] 手動トリガーで一度テスト実行済み

---

## 最終確認

- [ ] `PUBLISH_ENABLED=true` に変更する前に上記すべてが完了している
- [ ] 最初の投稿は1件のみで試験し、結果を確認してから量産
- [ ] Discord 通知が届くことを確認

---

## Phase 3 実装順序（参考）

1. X 投稿（最小構成）
2. 投稿後インサイト取得
3. Threads 投稿
4. category_scores 自動集計
5. learning_rules 自動生成
6. GitHub Actions 自動実行

詳細は `docs/next-phase-plan.md` を参照。
