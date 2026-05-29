# Publisher 認証情報設計

Phase 3-C で設計した SNS 投稿 API の認証情報について記述する。

---

## 重要ルール

- **APIキー・トークンの値は絶対にログに出力しない**
- `.env` の値を表示するコマンドは実行しない
- `config_loader.py` の `get_x_credentials()` / `get_threads_credentials()` は `_set` フラグのみ返す
- `check_publisher_credentials.py` は `[set]` / `[missing]` のみ表示し、値は表示しない

---

## X API 認証情報

### OAuth 1.0a（推奨・ユーザー代理投稿）

| 環境変数 | 取得場所 | 必須 |
|---|---|---|
| `X_API_KEY` | X Developer Portal → アプリ → Keys and Tokens | ✓ |
| `X_API_SECRET` | X Developer Portal → アプリ → Keys and Tokens | ✓ |
| `X_ACCESS_TOKEN` | X Developer Portal → アプリ → User authentication settings | ✓ |
| `X_ACCESS_TOKEN_SECRET` | X Developer Portal → アプリ → User authentication settings | ✓ |

### OAuth 2.0（代替方式）

| 環境変数 | 取得場所 | 必須 |
|---|---|---|
| `X_CLIENT_ID` | X Developer Portal → OAuth 2.0 設定 | ✓ |
| `X_CLIENT_SECRET` | X Developer Portal → OAuth 2.0 設定 | ✓ |
| `X_OAUTH2_ACCESS_TOKEN` | PKCE フロー後に取得 | ✓ |
| `X_OAUTH2_REFRESH_TOKEN` | PKCE フロー後に取得（長期運用） | 任意 |
| `X_REDIRECT_URI` | Developer Portal に登録したコールバック URI | 任意 |

### その他

| 環境変数 | 用途 |
|---|---|
| `X_BEARER_TOKEN` | 読み取り専用（タイムライン取得等）。投稿には不要。 |

---

## Threads API 認証情報

| 環境変数 | 取得場所 | 必須 |
|---|---|---|
| `THREADS_ACCESS_TOKEN` | Meta Developer → Threads API → アクセストークン発行 | ✓ |
| `THREADS_USER_ID` | アクセストークン検証後に取得する数値 ID | ✓ |
| `THREADS_APP_ID` | Meta Developer → アプリ → アプリ ID | 任意 |
| `THREADS_APP_SECRET` | Meta Developer → アプリ → アプリシークレット | 任意 |
| `THREADS_API_VERSION` | API バージョン（デフォルト: `v1.0`） | 任意 |

---

## 安全ガード環境変数

| 環境変数 | 意味 | Phase 3-C |
|---|---|---|
| `PUBLISH_ENABLED` | 全 SNS 投稿の ON/OFF | `false` 維持 |
| `ALLOW_REAL_X_POST` | X への本番投稿許可 | `false` 維持（Phase 3-D まで） |
| `ALLOW_REAL_THREADS_POST` | Threads への本番投稿許可 | `false` 維持（Phase 3-E まで） |

---

## 認証情報確認コマンド

```bash
# 両プラットフォームの確認
python scripts/check_publisher_credentials.py

# X のみ
python scripts/check_publisher_credentials.py --platform x

# Threads のみ
python scripts/check_publisher_credentials.py --platform threads
```

### 判定の読み方

| 判定 | 意味 |
|---|---|
| `READY_FOR_DRY_RUN` | 安全ガード OK、dry-run は動く（本番投稿不可） |
| `READY_FOR_CREDENTIAL_TEST` | 必要な認証情報がセット済み（API 接続はまだしない） |
| `NOT_READY` | 必須認証情報が不足している |

---

## .env への設定手順

```bash
# テンプレートをコピー
cp v2/.env.template v2/.env

# .env を編集して各値を入れる（値はログに出さない）
# X OAuth 1.0a の場合:
# X_API_KEY=xxxxx
# X_API_SECRET=xxxxx
# X_ACCESS_TOKEN=xxxxx
# X_ACCESS_TOKEN_SECRET=xxxxx
```

---

## X API Developer Account 取得手順（Phase 3-D 前に必要）

1. [developer.x.com](https://developer.x.com) にアクセス
2. 「Sign up for free account」で Essential プラン（無料）を申請
3. アプリを作成し、「User authentication settings」で OAuth 1.0a を有効化
4. `Read and Write` パーミッションを設定
5. Keys and Tokens から API Key/Secret、Access Token/Secret を取得
6. `.env` に設定し、`check_publisher_credentials.py --platform x` で確認

### Rate Limit（Free Tier）

| 種別 | 制限 |
|---|---|
| 投稿（POST /tweets） | 月 500 件 |
| 読み取り | 月 1 万件（Essential） |

---

## Threads API アクセストークン取得手順（Phase 3-E 前に必要）

1. [developers.facebook.com](https://developers.facebook.com) で Meta App を作成
2. Threads API プロダクトを追加
3. Threads ユーザーとして認証し、アクセストークンを発行
4. 長期トークンに変換（60日有効 → 延長可能）
5. `.env` に設定し、`check_publisher_credentials.py --platform threads` で確認
