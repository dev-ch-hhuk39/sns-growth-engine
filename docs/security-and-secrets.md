# シークレット管理方針

**最終更新**: 2026-05-29

---

## 絶対にコミットしてはいけないもの

以下のファイル・情報は `.gitignore` で除外済みです。**絶対にコミットしないでください。**

| ファイル / 変数 | 内容 |
|---|---|
| `.env` | 全APIキー・シークレットの実値 |
| `GCP_SA_JSON` / `SA_JSON_BASE64` | Google Cloud サービスアカウント JSON |
| `GEMINI_API_KEY` | Gemini API キー |
| `SNS_MASTER_SHEET_ID` | Google Sheets ID |
| `X_API_KEY` / `X_API_SECRET` | X (Twitter) API キー |
| `X_ACCESS_TOKEN` / `X_ACCESS_TOKEN_SECRET` | X アクセストークン |
| `THREADS_ACCESS_TOKEN` | Threads アクセストークン |
| `CLOUDINARY_API_SECRET` | Cloudinary シークレット |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL |
| `service-account*.json` | GCP サービスアカウント JSON ファイル |
| `credentials*.json` | 認証情報 JSON |
| `*.pem` / `*.key` / `*.b64` | 秘密鍵・証明書 |

---

## ローカル開発での設定方法

```bash
# テンプレートをコピーして設定
cp .env.template .env

# .env を編集して実値を設定（エディタで開く）
# nano .env または code .env など
```

`.env.template` に変数名と説明のみが記載されています。実値は **絶対に** `.env.template` に書かないでください。

---

## GitHub Actions での管理方針

本番運用では、シークレットは **GitHub Actions Secrets** で管理します。

### 設定場所
`GitHub Repository > Settings > Secrets and variables > Actions`

### 登録すべき Secrets

| Secret 名 | 用途 |
|---|---|
| `GCP_SA_JSON` | Google Cloud サービスアカウント（JSON文字列） |
| `GEMINI_API_KEY` | Gemini API キー |
| `SNS_MASTER_SHEET_ID` | Google Sheets ID |
| `X_API_KEY` | X API キー |
| `X_API_SECRET` | X API シークレット |
| `X_ACCESS_TOKEN` | X アクセストークン |
| `X_ACCESS_TOKEN_SECRET` | X アクセストークンシークレット |
| `THREADS_ACCESS_TOKEN` | Threads アクセストークン |
| `CLOUDINARY_URL` | Cloudinary 接続URL |
| `DISCORD_WEBHOOK_URL` | Discord 通知 Webhook |

### Workflow での参照方法

```yaml
env:
  GCP_SA_JSON: ${{ secrets.GCP_SA_JSON }}
  GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
  X_API_KEY: ${{ secrets.X_API_KEY }}
```

---

## push 前のセキュリティチェックコマンド

コミット・push 前に必ず以下を実行してください。

```bash
# .envがステージングに含まれていないことを確認
git status --short | grep -E "^(A|M|AM)\s+\.env" && echo "⛔ .envがコミット対象に含まれています！" || echo "✅ .env はステージングなし"

# APIキーらしき実値がソースコードに含まれていないことを確認
grep -rn "AIzaSy[0-9A-Za-z_-]{35}" . --include="*.py" 2>/dev/null && echo "⛔ Gemini APIキーらしき文字列を検出！" || true
grep -rn "AAAA[0-9A-Za-z_-]{20}" . --include="*.py" 2>/dev/null && echo "⛔ Twitterトークンらしき文字列を検出！" || true

# コミット予定ファイルの確認
git diff --cached --name-only

# .envが除外されていることを確認
git check-ignore -v .env
```

---

## 誤ってコミットした場合の対処

**.env や秘密情報をコミットしてしまった場合は、即座に以下を実施してください。**

1. **API キーをすべて無効化・再発行**する（GitHub は公開前でもスキャンします）
2. git history からファイルを削除する（`git filter-repo` または `BFG Repo Cleaner`）
3. force push（リモートにpush済みの場合）
4. 関係者に通知

**コードの削除だけでは不十分です。必ずキーを再発行してください。**

---

## 安全ガード（投稿制御）

SNS本番投稿を防ぐための4層ガードが実装されています。

```
Layer 1: PUBLISH_ENABLED=false  （デフォルト: 全投稿無効）
Layer 2: ALLOW_REAL_X_POST=false （デフォルト: X投稿無効）
Layer 2: ALLOW_REAL_THREADS_POST=false （デフォルト: Threads投稿無効）
Layer 3: --confirm-real-post フラグ（publish_queue.py 実行時）
Layer 4: --max-real-posts N（最大投稿件数上限）
```

詳細: `docs/safety-guards.md`
