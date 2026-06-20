# Credential Migration Plan

## 概要

- 作成日: 2026-06-20
- 目的: 旧3リポジトリから sns-growth-engine への認証情報の移行方針を定める
- 対象: X (Twitter) API 認証情報 / Threads API 認証情報 / GCP サービスアカウント

**セキュリティ絶対ルール:**
- 認証情報の値はこのドキュメントに記載しない
- `.env` ファイルはコミットしない
- GitHub Secrets の値は人間が直接確認する（AIに表示しない）
- rotate 前に必ず新 repo 側への設定を完了させる

---

## 旧 repo → 新 repo の env 名マッピング

### X (Twitter) 認証情報

| 旧 repo (X_autopost_yoru) | 新 repo (.env.template) | 備考 |
|---|---|---|
| `X_API_KEY` | `X_API_KEY` | 同名 |
| `X_API_SECRET` | `X_API_SECRET` | 同名 |
| `X_ACCESS_TOKEN` | `X_ACCESS_TOKEN` | 同名 |
| `X_ACCESS_TOKEN_SECRET` | `X_ACCESS_TOKEN_SECRET` | 同名 |

**対象アカウント: night_scout**

新 repo での使用箇所: `scripts/publish_x_post.py` → `src/publishers/x_publisher.py`

### Threads 認証情報 (night_scout)

| 旧 repo (threads_auto_post_gs) | 新 repo (.env.template) | 備考 |
|---|---|---|
| `THREADS_ACCESS_TOKEN` | `THREADS_ACCESS_TOKEN_NIGHT_SCOUT` | アカウント別に分離 |
| `THREADS_USER_ID` | `THREADS_USER_ID_NIGHT_SCOUT` | アカウント別に分離 |

### Threads 認証情報 (liver_manager)

| 旧 repo (threads-liver-coachhing) | 新 repo (.env.template) | 備考 |
|---|---|---|
| `THREADS_ACCESS_TOKEN` | `THREADS_ACCESS_TOKEN_LIVER_MANAGER` | アカウント別に分離 |
| `THREADS_USER_ID` | `THREADS_USER_ID_LIVER_MANAGER` | アカウント別に分離 |

> **Note:** 旧 repo では各 repo に 1アカウント分の `THREADS_ACCESS_TOKEN` だけが存在する。  
> 新 repo は複数アカウントを管理するため、`_NIGHT_SCOUT` / `_LIVER_MANAGER` サフィックスで分離する。

### GCP サービスアカウント

| 旧 repo | env 名 | 形式 | 新 repo での推奨 |
|---|---|---|---|
| X_autopost_yoru | `GCP_SA_JSON` | JSON文字列 | `GCP_SA_JSON` (同形式) |
| threads_auto_post_gs | `SA_JSON_BASE64` | base64エンコード | `SA_JSON_BASE64` (同形式) |
| threads-liver-coachhing | `SA_JSON_BASE64` | base64エンコード | `SA_JSON_BASE64` (同形式) |

> **Note:** 新 repo の `.env.template` には `SA_JSON_BASE64` と `GCP_SA_JSON` の両方が記載済み。  
> どちらか一方（または両方）を設定すれば動作する。読み込み順は `SA_JSON_BASE64` → `GCP_SA_JSON`。

### その他

| 旧 repo env 名 | 新 repo での扱い | 備考 |
|---|---|---|
| `SHEET_ID` / `SHEET_URL` | `SNS_MASTER_SHEET_ID` | 一元化（Task E で設計） |
| `SHEET_TAB` | 不要 | 新 repo は TAB_DEFINITIONS で自動管理 |
| `GEMINI_API_KEY` | `GEMINI_API_KEY` | 同名 |
| `DISCORD_WEBHOOK_URL` | `DISCORD_WEBHOOK_URL` | 同名 |
| `DEDUP_TAB` | 不要 | 新 repo は dedup を sheets schema で管理 |

---

## Threads トークンリフレッシュ保存先

旧 repo: GitHub Actions の `GITHUB_OUTPUT` に書き出し（次のワークフローステップで使用）  
新 repo: ローカルの JSON ファイルに保存（`.gitignore` 対象）

推奨ファイルパス:
```
data/threads_tokens/night_scout.json
data/threads_tokens/liver_manager.json
```

形式:
```json
{
  "access_token": "<value>",
  "refreshed_at": "2026-06-20T00:00:00+09:00",
  "expires_at": "2026-08-19T00:00:00+09:00"
}
```

> `data/` ディレクトリは `.gitignore` で除外済み。

env 変数との連携:
- 新 repo の `publish_threads_post.py` はまず `data/threads_tokens/{account_id}.json` を参照
- ファイルがなければ `THREADS_ACCESS_TOKEN_{ACCOUNT_ID}` 環境変数を参照
- どちらもなければ `THREADS_ACCESS_TOKEN` を参照（単一アカウント後方互換）

---

## .env.template への追加項目

以下の変数を `.env.template` に追加する（Task H 実装）:

```bash
# ============================================================
# Threads API 認証情報（アカウント別）
# 複数アカウントを管理する場合はアカウント別の変数を使用する。
# 単一アカウントの場合は THREADS_ACCESS_TOKEN / THREADS_USER_ID のみでも動作する。
# ============================================================
THREADS_ACCESS_TOKEN_NIGHT_SCOUT=
THREADS_USER_ID_NIGHT_SCOUT=
THREADS_ACCESS_TOKEN_LIVER_MANAGER=
THREADS_USER_ID_LIVER_MANAGER=

# ============================================================
# Threads トークンリフレッシュ設定
# THREADS_TOKEN_STORE_DIR: トークンJSONの保存先ディレクトリ（デフォルト: data/threads_tokens）
# ============================================================
THREADS_TOKEN_STORE_DIR=data/threads_tokens
```

---

## 移行手順（人間が実施）

### Phase 1: 新 repo .env に認証情報を設定

```bash
# 1. テンプレートをコピー
cp .env.template .env

# 2. エディタで以下の値を設定:
#    - X_API_KEY / X_API_SECRET / X_ACCESS_TOKEN / X_ACCESS_TOKEN_SECRET (night_scout)
#    - THREADS_ACCESS_TOKEN_NIGHT_SCOUT / THREADS_USER_ID_NIGHT_SCOUT
#    - THREADS_ACCESS_TOKEN_LIVER_MANAGER / THREADS_USER_ID_LIVER_MANAGER
#    - SA_JSON_BASE64 または GCP_SA_JSON
#    - SNS_MASTER_SHEET_ID
#    - GEMINI_API_KEY
```

### Phase 2: dry-run で動作確認

```bash
# X publisher dry-run
python3 scripts/publish_x_post.py \
  --account-id night_scout \
  --text "テスト" --confirm-post --dry-run

# Threads publisher dry-run (Phase 3-E 実装後)
python3 scripts/publish_threads_post.py \
  --account-id night_scout \
  --text "テスト" --confirm-post --dry-run

python3 scripts/publish_threads_post.py \
  --account-id liver_manager \
  --text "テスト" --confirm-post --dry-run
```

### Phase 3: 旧 repo の GitHub Actions を停止

`docs/legacy-repo-shutdown-plan.md` の手順に従う。

### Phase 4: 本番投稿テスト（1件のみ）

```bash
# .env に PUBLISH_ENABLED=true を一時的に追加（コミットしない）
PUBLISH_ENABLED=true ALLOW_REAL_X_POST=true \
python3 scripts/publish_x_post.py \
  --account-id night_scout \
  --text "<確定テキスト>" \
  --confirm-post --no-dry-run
```

### Phase 5: secret rotate（任意、30日後以降）

旧 repo の GitHub Secrets を削除し、新しいトークンを発行して新 repo の `.env` に設定する。

---

## トークン有効期限の管理

| 認証情報 | 有効期限 | 期限切れ前アクション |
|---|---|---|
| `X_ACCESS_TOKEN` | 無期限（revoke されるまで） | 定期ローテーション推奨 |
| `THREADS_ACCESS_TOKEN` (各アカウント) | 60日 | 45日後に `scripts/refresh_threads_token.py` を実行 |
| GCP サービスアカウント | 無期限（revoke されるまで） | 年次ローテーション推奨 |

Threads トークンリフレッシュのリマインダー設定推奨:
- 取得日から45日後にリフレッシュ実行
- `scripts/refresh_threads_token.py --account-id night_scout --confirm-refresh`
- `scripts/refresh_threads_token.py --account-id liver_manager --confirm-refresh`

---

## 関連ドキュメント

- `docs/legacy-repo-migration-audit.md`: 旧 repo の詳細調査
- `docs/legacy-repo-shutdown-plan.md`: 旧 repo 停止手順
- `docs/production-launch-checklist.md`: 本番開始チェックリスト
