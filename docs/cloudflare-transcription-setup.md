# Cloudflare 文字起こしセットアップガイド

**作成日**: 2026-06-06

---

## 概要

Cloudflare Workers AI の Whisper モデルを使って動画の文字起こしを行う。

---

## 必要な環境変数

`.env` ファイルに以下を設定する。

```env
# Cloudflare Workers AI
CLOUDFLARE_ACCOUNT_ID=your_account_id_here
CLOUDFLARE_API_TOKEN=your_api_token_here

# 文字起こし API の実行許可（デフォルト: false）
ALLOW_TRANSCRIPTION_API=false
```

`.env.template` を参考に設定する。

---

## 取得手順

### CLOUDFLARE_ACCOUNT_ID

1. [Cloudflare ダッシュボード](https://dash.cloudflare.com/) にログイン
2. 右サイドバーの「Account ID」をコピー

### CLOUDFLARE_API_TOKEN

1. 「My Profile」→「API Tokens」→「Create Token」
2. 「Workers AI」権限を付与する
3. トークンをコピー

---

## 日次上限

| 設定 | デフォルト値 | 変更方法 |
|---|---|---|
| `DAILY_TRANSCRIPTION_LIMIT_MINUTES` | 120分 | `.env` に設定 |

120分を超えると自動的にスキップされる。`transcription_runs` タブで累計を管理する。

---

## 動作確認

### 1. 認証情報チェック（API 呼び出しなし）

```bash
python scripts/test_cloudflare_transcription_credentials.py
```

### 2. スモークテスト（実 API 呼び出し）

詳細: `docs/cloudflare-transcription-smoke-test.md`

---

## 安全ガード

| 設定 | 値 |
|---|---|
| デフォルト | `ALLOW_TRANSCRIPTION_API=false`（実API禁止） |
| 実API許可 | `ALLOW_TRANSCRIPTION_API=true` + `--confirm-api` |
| 日次上限 | 120分/日（`transcription_runs` タブで管理） |
