# Credential Migration Plan

## 概要

- 作成日: 2026-06-20
- 目的: 旧3リポジトリから sns-growth-engine への認証情報の移行方針

**セキュリティ絶対ルール:**
- 認証情報の値はこのドキュメントに記載しない（env 名のみ）
- `.env` ファイルはコミットしない
- GitHub Secrets の値は人間が直接確認する（AI に表示しない）
- rotate 前に必ず新 repo 側への設定を完了させる

---

## 旧 repo → 新 repo の env 名マッピング

### X (night_scout)

| 旧 repo (X_autopost_yoru) | 新 repo | 必須 | 設定先 | rotate 推奨 |
|---|---|---|---|---|
| `X_API_KEY` | `X_API_KEY` | 必須 | local .env | 移行完了後 |
| `X_API_SECRET` | `X_API_SECRET` | 必須 | local .env | 移行完了後 |
| `X_ACCESS_TOKEN` | `X_ACCESS_TOKEN` | 必須 | local .env | 移行完了後 |
| `X_ACCESS_TOKEN_SECRET` | `X_ACCESS_TOKEN_SECRET` | 必須 | local .env | 移行完了後 |

安全フラグ（本番投稿時のみ .env に設定。永続 commit 禁止）:
```
PUBLISH_ENABLED=false      # デフォルト false
ALLOW_REAL_X_POST=false    # デフォルト false
```

### Threads (night_scout)

| 旧 repo (threads_auto_post_gs) | 新 repo | 必須 | 設定先 | rotate 推奨 |
|---|---|---|---|---|
| `THREADS_ACCESS_TOKEN` | `THREADS_ACCESS_TOKEN_NIGHT_SCOUT` | 必須 | local .env | 高（60日期限） |
| `THREADS_USER_ID` | `THREADS_USER_ID_NIGHT_SCOUT` | 必須 | local .env | 移行完了後 |
| — | `THREADS_APP_ID` | 任意 | local .env | — |
| — | `THREADS_APP_SECRET` | 任意 | local .env | — |
| — | `THREADS_API_VERSION` | 任意 | local .env | — |

安全フラグ:
```
ALLOW_REAL_THREADS_POST=false    # デフォルト false
```

### Threads (liver_manager)

| 旧 repo (threads-liver-coachhing) | 新 repo | 必須 | 設定先 | rotate 推奨 |
|---|---|---|---|---|
| `THREADS_ACCESS_TOKEN` | `THREADS_ACCESS_TOKEN_LIVER_MANAGER` | 必須 | local .env | 高（60日期限） |
| `THREADS_USER_ID` | `THREADS_USER_ID_LIVER_MANAGER` | 必須 | local .env | 移行完了後 |

> **注意:** night_scout と liver_manager の `THREADS_ACCESS_TOKEN` は別の値。  
> 旧 repo では同名変数 `THREADS_ACCESS_TOKEN` を別々の repo に設定していた。  
> 新 repo ではアカウント名サフィックスで分離する。

### Google Sheets

| 旧 repo | 旧 env 名 | 新 repo env 名 | 必須 | 備考 |
|---|---|---|---|---|
| 各 repo の SHEET_ID/SHEET_URL | `SHEET_ID` / `SHEET_URL` | `SNS_MASTER_SHEET_ID` | 必須 | 新規作成推奨 |
| threads_auto_post_gs / threads-liver | `SA_JSON_BASE64` | `SA_JSON_BASE64` | どちらか必須 | base64 形式 |
| X_autopost_yoru | `GCP_SA_JSON` | `GCP_SA_JSON` | どちらか必須 | JSON 文字列形式 |

> `SA_JSON_BASE64` か `GCP_SA_JSON` のどちらかが設定されていれば動作する。

### Gemini

| 旧 env 名 | 新 repo env 名 | 必須 |
|---|---|---|
| `GEMINI_API_KEY` | `GEMINI_API_KEY` | 必須 |
| — | `GEMINI_MODEL` | 任意 |
| — | `GEMINI_MODEL_CANDIDATES` | 任意 |

### Cloudinary（初期 OFF）

| env 名 | 必須 | 安全フラグ |
|---|---|---|
| `CLOUDINARY_CLOUD_NAME` | Cloudinary 有効化時 | `ALLOW_CLOUDINARY_UPLOAD=false` |
| `CLOUDINARY_API_KEY` | Cloudinary 有効化時 | — |
| `CLOUDINARY_API_SECRET` | Cloudinary 有効化時 | — |

### Cloudflare Workers AI / transcription（初期 OFF）

| env 名 | 必須 | 安全フラグ |
|---|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | transcription 有効化時 | `ALLOW_TRANSCRIPTION_API=false` |
| `CLOUDFLARE_API_TOKEN` | transcription 有効化時 | — |
| `DAILY_TRANSCRIPTION_MINUTES_LIMIT` | 任意 | デフォルト: 120分 |
| `TRANSCRIPTION_PROVIDER` | 任意 | デフォルト: `cloudflare_whisper` |

---

## Threads トークン保存設計

旧 repo: GitHub Secrets 経由で GITHUB_OUTPUT に書き出し  
新 repo: `data/threads_tokens/{account_id}.json` にローカル保存（`.gitignore` 対象）

保存形式:
```json
{
  "access_token": "...",
  "refreshed_at": "2026-06-20T00:00:00+09:00",
  "expires_at": "2026-08-19T00:00:00+09:00",
  "account_id": "night_scout"
}
```

token 読み込み優先順位（`threads_publisher.py`）:
1. `data/threads_tokens/{account_id}.json`
2. `THREADS_ACCESS_TOKEN_{ACCOUNT_ID_UPPER}` 環境変数
3. `THREADS_ACCESS_TOKEN` 環境変数（後方互換）

リフレッシュスクリプト:
```bash
python3 scripts/refresh_threads_token.py --account-id night_scout --dry-run
python3 scripts/refresh_threads_token.py --account-id night_scout --confirm-refresh
python3 scripts/refresh_threads_token.py --account-id liver_manager --confirm-refresh
```

---

## 移行手順（人間が実施）

### Step 1: 新 repo .env に認証情報を設定

```bash
cp .env.template .env
# エディタで値を設定:
#   X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET
#   THREADS_ACCESS_TOKEN_NIGHT_SCOUT / THREADS_USER_ID_NIGHT_SCOUT
#   THREADS_ACCESS_TOKEN_LIVER_MANAGER / THREADS_USER_ID_LIVER_MANAGER
#   SA_JSON_BASE64 または GCP_SA_JSON
#   SNS_MASTER_SHEET_ID
#   GEMINI_API_KEY
```

### Step 2: readiness チェック

```bash
python3 scripts/check_credentials_readiness.py
```

### Step 3: dry-run で動作確認

```bash
# X publisher dry-run
python3 scripts/publish_x_post.py --account-id night_scout --text "テスト" --confirm-post --dry-run

# Threads publisher dry-run
python3 scripts/publish_threads_post.py --account-id night_scout --text "テスト" --confirm-post --dry-run
python3 scripts/publish_threads_post.py --account-id liver_manager --text "テスト" --confirm-post --dry-run
```

### Step 4: Threads token refresh（初回設定）

```bash
# 旧 repo の THREADS_ACCESS_TOKEN 値を新 repo の .env に設定後
python3 scripts/refresh_threads_token.py --account-id night_scout --confirm-refresh
python3 scripts/refresh_threads_token.py --account-id liver_manager --confirm-refresh
```

### Step 5: 本番投稿（1件ずつ承認制）

旧 repo 停止確認後（`docs/legacy-repo-shutdown-plan.md` 参照）:
```bash
# .env に PUBLISH_ENABLED=true ALLOW_REAL_X_POST=true を一時追加
python3 scripts/publish_x_post.py --account-id night_scout --text "..." --confirm-post --no-dry-run
```

### Step 6: rotate（30日後以降）

- Threads: `scripts/refresh_threads_token.py` で新トークン取得 → 旧 repo Secrets 削除
- X: Twitter Developer Portal で新 Access Token 生成 → 旧 repo Secrets 削除

---

## トークン有効期限管理

| 認証情報 | 有効期限 | 期限前アクション |
|---|---|---|
| X_ACCESS_TOKEN | 無期限（revoke まで） | 年次 rotate 推奨 |
| THREADS_ACCESS_TOKEN (night_scout) | 60日 | 45日後にリフレッシュ |
| THREADS_ACCESS_TOKEN (liver_manager) | 60日 | 45日後にリフレッシュ |
| GCP Service Account | 無期限（revoke まで） | 年次 rotate 推奨 |

---

## 関連ドキュメント

- `docs/legacy-repo-migration-audit.md`: 旧 repo 詳細調査
- `docs/legacy-repo-shutdown-plan.md`: 旧 repo 停止手順
- `docs/setup-new-sns-master-sheet.md`: 新規シート作成手順
- `docs/production-launch-checklist.md`: 本番開始チェックリスト
