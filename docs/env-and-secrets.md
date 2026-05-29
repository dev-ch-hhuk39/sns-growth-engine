# 環境変数・シークレット管理

## .env ファイル構成

`.env.template` をコピーして `.env` を作成する。`.env` は `.gitignore` で除外済み。

```bash
cp v2/.env.template v2/.env
```

---

## 必須環境変数

### SNS_MASTER_SHEET_ID

統合スプレッドシートのIDを設定する。
スプレッドシートURLの `https://docs.google.com/spreadsheets/d/{ID}/edit` の部分。

```env
SNS_MASTER_SHEET_ID=1AbC...xyz
```

旧名称 `NOTE_MASTER_SHEET_ID` は後方互換として残してあるが、新規設定は `SNS_MASTER_SHEET_ID` を使うこと。

### GCP サービスアカウント認証（どちらか一方）

**SA_JSON_BASE64 方式**（ライバー・夜職threads アカウントで使用）:

```bash
# JSON を base64 エンコードして .env に貼る
cat service-account.json | base64 | pbcopy  # macOS
```

```env
SA_JSON_BASE64=eyJ0eXBlIjoic2VydmljZV9hY2NvdW50IiwicHJvamVjdF...
```

**GCP_SA_JSON 方式**（夜職x アカウントで使用）:

```env
GCP_SA_JSON={"type":"service_account","project_id":"..."}
```

### GEMINI_API_KEY

Google AI Studio または Vertex AI から取得。

```env
GEMINI_API_KEY=AIzaSy...
```

---

## 任意環境変数

| 変数 | デフォルト | 説明 |
|---|---|---|
| `GEMINI_MODEL_CANDIDATES` | `gemini-2.5-flash-lite@v1beta,...` | モデル優先順位（カンマ区切り） |
| `GEMINI_MODEL` | `gemini-2.5-flash` | 単一モデル指定（CANDIDATES が優先） |
| `DISCORD_WEBHOOK_URL` | 空 | Discord 通知用 Webhook URL |

---

## 安全ガード環境変数

| 変数 | デフォルト | 意味 |
|---|---|---|
| `DRY_RUN` | `false` | true: 書き込み & LLM 両方モック |
| `MOCK_LLM` | `false` | true: LLM のみモック |
| `MOCK_SHEETS` | `false` | true: Sheets を MockSheetsClient に強制切替 |
| `PUBLISH_ENABLED` | `false` | true: SNS 投稿処理を有効化（Phase 3 以降） |

---

## GitHub Secrets での管理（Phase 3 以降）

GitHub Actions でのシークレット設定名:

| Secret 名 | 対応する .env 変数 |
|---|---|
| `SNS_MASTER_SHEET_ID` | `SNS_MASTER_SHEET_ID` |
| `SA_JSON_BASE64` | `SA_JSON_BASE64` |
| `GEMINI_API_KEY` | `GEMINI_API_KEY` |
| `DISCORD_WEBHOOK_URL` | `DISCORD_WEBHOOK_URL` |

---

## セキュリティ注意事項

- `.env` をコミットしない（`.gitignore` に含まれていることを確認）
- APIキー・サービスアカウントJSON をログやエラーメッセージに出力しない
- `GCP_SA_JSON` をコマンドライン引数で渡さない（`ps` コマンドで見える）
- サービスアカウントの権限は必要最小限に絞る（Sheets 読み書きのみ）
