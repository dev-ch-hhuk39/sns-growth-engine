# Threads トークン自動リフレッシュ

## 概要

- 作成日: 2026-06-21
- 目的: Threads 長期アクセストークン (60日期限) の自動リフレッシュ手順と GitHub Actions ワークフローの説明

Threads の長期アクセストークンは **60日で期限切れ** になる。  
このシステムでは以下の2つの方法でリフレッシュできる。

1. **手動リフレッシュ** (`scripts/refresh_threads_token.py`)
2. **GitHub Actions 自動リフレッシュ** (`.github/workflows/refresh-threads-tokens.yml`)

---

## セキュリティルール（絶対遵守）

- トークン値・app_secret 値を echo / print / log しない
- `data/threads_tokens/` を git commit しない（`.gitignore` で保護済み）
- `.env` を git commit しない
- GitHub Actions ログにトークン値を出力しない
- リフレッシュ失敗時に古いトークンを削除しない
- GitHub Secrets 更新はリフレッシュ成功後のみ

---

## 認証情報の設計

### 環境変数の優先順位

| フィールド | 優先1 | 優先2 | フォールバック |
|---|---|---|---|
| access_token | `data/threads_tokens/{account_id}.json` | `THREADS_ACCESS_TOKEN_{UPPER}` | `THREADS_ACCESS_TOKEN` |
| user_id | `THREADS_USER_ID_{UPPER}` | file | `THREADS_USER_ID` |
| app_id | `THREADS_APP_ID_{UPPER}` | file | `THREADS_APP_ID` |
| app_secret | `THREADS_APP_SECRET_{UPPER}` | file | `THREADS_APP_SECRET` |

### アカウント別変数名

| アカウント | 変数名 |
|---|---|
| night_scout | `THREADS_ACCESS_TOKEN_NIGHT_SCOUT`, `THREADS_USER_ID_NIGHT_SCOUT`, `THREADS_APP_ID_NIGHT_SCOUT`, `THREADS_APP_SECRET_NIGHT_SCOUT` |
| liver_manager | `THREADS_ACCESS_TOKEN_LIVER_MANAGER`, `THREADS_USER_ID_LIVER_MANAGER`, `THREADS_APP_ID_LIVER_MANAGER`, `THREADS_APP_SECRET_LIVER_MANAGER` |

### 認証情報リゾルバー

`src/publishers/threads_credentials.py` に共通リゾルバーを実装。

```python
from publishers.threads_credentials import resolve_credentials

creds = resolve_credentials("night_scout")
# creds = {"app_id": "...", "app_secret": "...", "access_token": "...", "user_id": "..."}
```

---

## トークンリフレッシュの仕組み

Threads 長期アクセストークンは以下の API でリフレッシュできる。

```
GET https://graph.threads.net/refresh_access_token
  ?grant_type=th_refresh_token
  &access_token=<現在のトークン>
```

- **app_id / app_secret は不要**（長期トークンの自己リフレッシュのみ）
- リフレッシュ後は新しいトークンが返る（旧トークンは即時無効）
- 新しい有効期限: リフレッシュ後 60日

---

## 手動リフレッシュ

### dry-run（状態確認のみ）

```bash
python3 scripts/refresh_threads_token.py --account-id night_scout --dry-run
python3 scripts/refresh_threads_token.py --account-id liver_manager --dry-run
```

### 実際のリフレッシュ

```bash
# ⚠️ 旧トークンが即時無効になる。実行前に GitHub Secrets 更新の準備を。
python3 scripts/refresh_threads_token.py --account-id night_scout --confirm-refresh
python3 scripts/refresh_threads_token.py --account-id liver_manager --confirm-refresh
```

リフレッシュ後は `data/threads_tokens/{account_id}.json` に保存される。  
このファイルから GitHub Secrets に反映するには次のステップを手動で行う:

```bash
# 値はパイプ経由で渡す（echo でログに出さない）
jq -r '.access_token' data/threads_tokens/night_scout.json \
  | gh secret set THREADS_ACCESS_TOKEN_NIGHT_SCOUT --repo <owner/repo>
```

---

## GitHub Actions による自動リフレッシュ

### スケジュール

- 毎週日曜 2:00 UTC (11:00 JST) に自動実行
- 60日期限 → 45日前に実行することを想定（週次なので余裕あり）

### 必要な GitHub Secrets

| シークレット名 | 説明 | 必須 |
|---|---|---|
| `THREADS_ACCESS_TOKEN_NIGHT_SCOUT` | night_scout アクセストークン | ✅ |
| `THREADS_ACCESS_TOKEN_LIVER_MANAGER` | liver_manager アクセストークン | ✅ |
| `THREADS_USER_ID_NIGHT_SCOUT` | night_scout Threads ユーザー ID | ✅ |
| `THREADS_USER_ID_LIVER_MANAGER` | liver_manager Threads ユーザー ID | ✅ |
| `THREADS_APP_ID_NIGHT_SCOUT` | night_scout Meta App ID | 推奨 |
| `THREADS_APP_SECRET_NIGHT_SCOUT` | night_scout Meta App Secret | 推奨 |
| `THREADS_APP_ID_LIVER_MANAGER` | liver_manager Meta App ID | 推奨 |
| `THREADS_APP_SECRET_LIVER_MANAGER` | liver_manager Meta App Secret | 推奨 |
| `GH_SECRET_WRITE_TOKEN` | PAT (secrets:write スコープ) | ✅ Secret 更新に必須 |
| `DISCORD_WEBHOOK_URL` | 通知先 Discord Webhook URL | 任意 |

### GH_SECRET_WRITE_TOKEN の取得方法

1. GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens
2. 「Generate new token」
3. Repository access: 対象 repo のみ
4. Permissions → Secrets: **Read and write**
5. 生成したトークンを GitHub Secrets の `GH_SECRET_WRITE_TOKEN` に設定

> ⚠️ `GITHUB_TOKEN` (GitHub Actions の自動トークン) は `secrets:write` 権限がないため、  
> GitHub Secrets の更新には使えない。必ず別途 PAT を作成すること。

### 手動実行（workflow_dispatch）

GitHub Actions → "Refresh Threads Tokens" → "Run workflow" で以下を指定:

| 入力 | 説明 | 例 |
|---|---|---|
| account | 対象アカウント | `all` / `night_scout` / `liver_manager` |
| dry_run | dry-run モード | `true`（状態確認のみ） / `false`（実際に更新） |

### トークン更新フロー（dry_run=false の場合）

```
1. Python スクリプト実行
   → Threads API 呼び出し → 新トークン取得
   → data/threads_tokens/{account_id}.json に保存
2. GitHub Secret 更新
   → jq でトークン抽出（値はパイプのみ、ログ出力なし）
   → gh secret set でリポジトリ Secret 更新
3. Discord 通知（URL 設定済みの場合）
```

---

## 障害対応

### トークンが期限切れになった場合

1. Graph API Explorer (https://developers.facebook.com/tools/explorer/) で新しいトークンを取得
2. `.env` の `THREADS_ACCESS_TOKEN_*` を更新
3. GitHub Secrets の `THREADS_ACCESS_TOKEN_*` を手動更新
4. `python3 scripts/refresh_threads_token.py --account-id <id> --dry-run` で状態確認

### refresh_threads_token.py がエラーになる場合

- `ERROR: THREADS_ACCESS_TOKEN が見つかりません` → `.env` または `data/threads_tokens/` を確認
- HTTP 400 / 401 → トークンが既に期限切れの可能性。上記「期限切れ対応」を参照
- HTTP 429 → Rate Limit。数時間後に再試行

### GitHub Actions が Secret 更新に失敗する場合

- `READY_WITH_MISSING_GH_SECRET_WRITE_TOKEN` → PAT を生成して `GH_SECRET_WRITE_TOKEN` に設定
- `ERROR: TOKEN_FILE が見つかりません` → Python スクリプトのリフレッシュが失敗。ログを確認

---

## 関連ドキュメント

- `docs/credential-migration-plan.md` — 認証情報管理の全体像
- `docs/free-tier-operations-audit.md` — Threads API コスト監査
- `docs/legacy-repo-shutdown-plan.md` — 旧リポジトリ停止状況
- `scripts/refresh_threads_token.py` — リフレッシュスクリプト
- `src/publishers/threads_credentials.py` — 認証情報リゾルバー
- `.github/workflows/refresh-threads-tokens.yml` — 自動リフレッシュワークフロー
