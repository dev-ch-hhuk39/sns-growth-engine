# トラブルシューティング

よくあるエラーと対処法をまとめる。

---

## 環境変数

### `SNS_MASTER_SHEET_ID が未設定です`

```
ValueError: SNS_MASTER_SHEET_ID が未設定です。
```

**原因:** `.env` にスプレッドシート ID が設定されていない  
**対処:**
```bash
python scripts/print_env_status.py  # 未設定項目を確認
# .env に SNS_MASTER_SHEET_ID=<ID> を追加
```

### `GCP認証情報が未設定です`

**原因:** `SA_JSON_BASE64` も `GCP_SA_JSON` も設定されていない  
**対処:**
```bash
# base64 でエンコードする場合（macOS）
cat service-account.json | base64 | pbcopy
# .env に SA_JSON_BASE64=<コピーした値> を追加
```

### `.env` の内容が読まれない

**原因:** `python-dotenv` が未インストール、または `.env` が `v2/` フォルダにない  
**対処:**
```bash
pip install python-dotenv
ls v2/.env  # ファイルの存在確認
```

---

## Gemini API エラー

### `Gemini API エラー (HTTP 400)`

**原因:** プロンプトが長すぎる、またはモデル名が間違っている  
**対処:**
```bash
# .env.template の GEMINI_MODEL_CANDIDATES を確認
# GEMINI_MODEL=gemini-2.5-flash が正しいか確認
```

### `Gemini API エラー (HTTP 403)`

**原因:** API キーが無効、または Gemini API が有効になっていない  
**対処:**
1. Google AI Studio で API キーが有効か確認
2. `.env` の `GEMINI_API_KEY` が正しいか確認（スペース・改行がないか）

### `Gemini API エラー (HTTP 429)`

**原因:** API レート制限超過  
**対処:** しばらく待ってから再実行する。Free Tier は制限が厳しい。

### `JSONパース失敗`

**原因:** Gemini がプロンプト通りの JSON を返さなかった  
**対処:** 一時的な現象なら再実行で解決する。繰り返す場合はプロンプトを確認。

---

## Google Sheets エラー

### `gspread.exceptions.APIError: {'code': 403}`

**原因:** サービスアカウントにスプレッドシートへのアクセス権限がない  
**対処:**
1. Google スプレッドシートを開く
2. 「共有」ボタンをクリック
3. サービスアカウントのメールアドレス（`xxxx@xxxx.iam.gserviceaccount.com`）を追加
4. 権限を「編集者」に設定

### `gspread.exceptions.SpreadsheetNotFound`

**原因:** スプレッドシート ID が間違っている  
**対処:**
1. スプレッドシートの URL を確認: `https://docs.google.com/spreadsheets/d/{ID}/edit`
2. `.env` の `SNS_MASTER_SHEET_ID` に ID 部分を設定

### `SA_JSON_BASE64 のデコードに失敗しました`

**原因:** base64 エンコードが正しくない、または改行が含まれている  
**対処:**
```bash
# macOS
cat service-account.json | base64 | tr -d '\n' | pbcopy
# Linux
cat service-account.json | base64 -w 0
```

### `GCP_SA_JSON のパースに失敗しました`

**原因:** JSON がそのまま貼り付けられているが形式が正しくない  
**対処:** サービスアカウント JSON ファイルをテキストエディタで開き、全体をそのまま `GCP_SA_JSON=` の後に貼る。

### `WorksheetNotFound: ワークシートが見つかりません`

**原因:** タブが初期化されていない  
**対処:**
```bash
python scripts/setup_and_verify.py --setup --verify
```

---

## パイプラインエラー

### `--test-write には --use-sheets が必要です`

**対処:** `--use-sheets --test-write` を一緒に指定する

### `--test-write と --dry-run は同時に指定できません`

**対処:** どちらか一方のみ指定する

### `認証情報（SA_JSON_BASE64 または GCP_SA_JSON）と SNS_MASTER_SHEET_ID が必要です`

**原因:** `--use-sheets` を指定したが認証情報が未設定  
**対処:** `.env` に認証情報を設定するか、`--use-sheets` を外してモックで実行する

### `generate_drafts: accounts が取得できません`

**原因:** `accounts` タブが空またはセットアップ未実施  
**対処:**
```bash
python scripts/setup_and_verify.py --setup
```

---

## テスト失敗

### `test_phase2.py: FAIL`

**確認方法:** エラーメッセージを確認する  
**よくある原因:**
- `seeds.py` の内容が変わった
- `publish_decision.py` のロジックが変更された
- `MockSheetsClient` のメソッドが欠けている

### `preflight_check.py: BLOCKED_BY_ENV`

**対処:** `python scripts/print_env_status.py` で未設定項目を確認し、`.env` に追加する

---

## Python バージョン関連

### `ModuleNotFoundError: No module named 'zoneinfo'`

**原因:** Python 3.9 未満を使っている（`zoneinfo` は 3.9 以降）  
**対処:** Python 3.11 以上をインストールする

### `ImportError: No module named 'gspread'`

**対処:**
```bash
pip install gspread google-auth google-auth-oauthlib
```

---

## セキュリティ関連

### APIキーを誤ってログに出力してしまった

**対処:**
1. 直ちに APIキーを無効化して再発行する
2. ログファイルを削除する
3. `.env` を再設定する

### `.env` を git にコミットしてしまった

**対処:**
1. 直ちに認証情報を再発行する
2. git から `.env` を削除: `git rm --cached .env`
3. `.gitignore` に `.env` が含まれているか確認
