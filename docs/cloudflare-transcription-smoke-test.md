# Cloudflare 文字起こし スモークテストガイド

**作成日**: 2026-06-06

---

## 概要

Cloudflare Whisper API が正しく動作するかを最小限の音声で確認する。

---

## コマンド

### ステップ 1: 認証情報チェック（API 呼び出しなし）

```bash
python scripts/test_cloudflare_transcription_credentials.py
```

確認項目:
- `CLOUDFLARE_ACCOUNT_ID` が設定されているか
- `CLOUDFLARE_API_TOKEN` が設定されているか
- `ALLOW_TRANSCRIPTION_API` の値

### ステップ 2: スモークテスト（実 API 呼び出し）

```bash
# .env に以下を設定してから実行
# ALLOW_TRANSCRIPTION_API=true
# CF_SMOKE_TEST_AUDIO_URL=<5秒以内の音声 URL>

ALLOW_TRANSCRIPTION_API=true python scripts/test_cloudflare_transcription_smoke.py \
  --use-api --confirm-api
```

---

## 前提条件

| 条件 | 設定方法 |
|---|---|
| `ALLOW_TRANSCRIPTION_API=true` | `.env` に設定 |
| `--use-api --confirm-api` の両フラグ | コマンドライン引数 |
| `CF_SMOKE_TEST_AUDIO_URL` | テスト用音声 URL（5秒以内推奨） |

---

## テスト用音声 URL の用意

5秒以内の WAV または MP3 ファイルを用意し、公開 URL として設定する。

```env
CF_SMOKE_TEST_AUDIO_URL=https://example.com/test_5sec.wav
```

---

## 成功時の出力例

```
[OK] スモークテスト成功
     status='done'
     transcript_length=42 chars
```

---

## タイムアウト設定

デフォルト: 30秒。長い音声ファイルは 5秒以内に切り詰めること。

---

## 安全ガード

- 本番環境では `ALLOW_TRANSCRIPTION_API=false` のままにする
- スモークテスト完了後は `ALLOW_TRANSCRIPTION_API=false` に戻す
- 日次120分上限は `transcription_runs` タブで管理される
