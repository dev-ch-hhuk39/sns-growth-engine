# セットアップチェックリスト

このチェックリストを上から順にこなしてください。

---

## 1. 環境準備

- [ ] Python 3.11 以上がインストールされている
  ```bash
  python3 --version  # 3.11+ を確認
  ```

- [ ] 必要なパッケージがインストールされている
  ```bash
  pip install gspread google-auth requests python-dotenv
  ```

- [ ] `v2/.env` が存在する
  ```bash
  cd v2
  cp .env.template .env
  ```

---

## 2. 認証情報の設定

### Google スプレッドシート

- [ ] Google スプレッドシートを新規作成（または既存のものを用意）
- [ ] スプレッドシート ID を `.env` に設定
  ```
  SNS_MASTER_SHEET_ID=1AbCdEfG...
  ```
- [ ] Google Cloud Console でサービスアカウントを作成
- [ ] サービスアカウントに スプレッドシートの編集権限を付与
- [ ] 認証 JSON を `.env` に設定（いずれか）
  ```
  SA_JSON_BASE64=eyJ0eXBl...   # base64 エンコード版
  GCP_SA_JSON={"type":"service_account",...}  # そのまま貼り付け版
  ```

### Gemini API

- [ ] Google AI Studio または Vertex AI で API キーを取得
- [ ] `.env` に設定
  ```
  GEMINI_API_KEY=AIzaSy...
  ```

---

## 3. 設定確認

- [ ] `python scripts/print_env_status.py` で必須項目がすべて `set`
- [ ] PUBLISH_ENABLED=false であることを確認

---

## 4. 接続テスト

- [ ] `python scripts/test_gemini_real.py` が PASS または SKIP で終了
- [ ] `python scripts/test_sheets_connection.py --dry-run` が PASS または SKIP で終了

---

## 5. Sheets セットアップ

- [ ] `python scripts/setup_and_verify.py --dry-run` で内容を確認
- [ ] `python scripts/setup_and_verify.py --setup --verify` でセットアップ実行
  - 12タブが作成される
  - accounts: night_scout / liver_manager が追加される
  - content_categories: 16件（各アカウント8件）が追加される
  - prompt_templates: 5件が追加される
  - distribution_rules: 4件が追加される
- [ ] `python scripts/setup_and_verify.py --test-write` でテスト書き込み確認

---

## 6. 総合診断

- [ ] `python scripts/preflight_check.py` の判定が `READY_FOR_*` になる

---

## 7. パイプライン検証

- [ ] `python scripts/run_pipeline.py --account-id night_scout --dry-run --use-sheets` が正常終了
  - `SHEETS_WRITE: false (dry-run)` が表示される
  - `SNS_POSTING: disabled` が表示される

- [ ] `python scripts/run_pipeline.py --account-id night_scout --use-sheets --test-write --limit 1` が正常終了
  - Sheets に draft / derivative / queue が書き込まれる
  - SNS には投稿されない

---

## 8. Phase 3 移行前最終確認

- [ ] `python scripts/test_phase2.py` が 31 PASS / 0 FAIL
- [ ] X Developer Account 取得済み
- [ ] Threads API アクセス取得済み
- [ ] `accounts.auto_publish` を `TRUE` に変更予定
- [ ] Phase 3 実装完了後に `PUBLISH_ENABLED=true` に変更予定

→ [Phase 3 go/no-go 判断基準](./phase3-go-no-go.md)

---

## スプレッドシートの手動確認ポイント

セットアップ後、Google スプレッドシートで以下を目視確認してください:

- [ ] `accounts` タブに night_scout / liver_manager がある
- [ ] `content_categories` タブにカテゴリが16件ある
- [ ] `prompt_templates` タブにテンプレートが5件ある
- [ ] `accounts.line_url` に正しい LINE URL を設定する
- [ ] `accounts.x_handle` / `accounts.threads_handle` を設定する
