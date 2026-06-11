# Cloudflare Transcription Runbook

## 1. 認証情報の設定項目

`.env` に以下を設定する:

```env
CLOUDFLARE_ACCOUNT_ID=your_account_id
CLOUDFLARE_API_TOKEN=your_api_token
ALLOW_TRANSCRIPTION_API=false   # 実行直前のみ true に変更
DAILY_TRANSCRIPTION_MINUTES_LIMIT=120
```

設定確認:
```bash
python scripts/test_cloudflare_transcription_credentials.py
```

## 2. 無料枠 120分/日 運用方針

- Cloudflare Workers AI Whisper の無料枠: 約 $0.005/分
- `DAILY_TRANSCRIPTION_MINUTES_LIMIT=120` で1日120分以内に制限
- 超過しそうな場合は `ALLOW_TRANSCRIPTION_API=false` に戻す
- 処理済み分数は `processed_minutes` で記録

## 3. 30秒smoke test用音声ファイルの作り方

```bash
# ffmpegで30秒の無音ファイル生成（smoke test用）
ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 30 tests/fixtures/smoke_audio_30s.mp3

# または既存の短い音声ファイルを30秒に切り出す
ffmpeg -i input.mp4 -ss 0 -t 30 -vn tests/fixtures/smoke_audio_30s.mp3
```

ファイル要件:
- 長さ: 30秒以内
- 形式: mp3 / wav / m4a / ogg / flac
- サイズ: 25MB以内（Cloudflare制限）

## 4. 実行コマンド

```bash
# Step 1: 認証情報確認（実API呼び出しなし・常時安全）
python scripts/test_cloudflare_transcription_credentials.py

# Step 2: smoke test（実API呼び出しには以下が全て必要）
# - ALLOW_TRANSCRIPTION_API=true に変更後
# - --use-api --confirm-api を指定
python scripts/test_cloudflare_transcription_smoke.py \
  --audio-file tests/fixtures/smoke_audio_30s.mp3 \
  --use-api \
  --confirm-api

# Step 3: 実行後すぐに false へ戻す（下記 Step 5参照）
```

## 5. 実行後に ALLOW_TRANSCRIPTION_API=false へ戻す手順

実API実行後は**必ず**以下を実施する:

```bash
# .env を開いて ALLOW_TRANSCRIPTION_API=false に戻す
# または:
python -c "
import re, pathlib
env = pathlib.Path('.env').read_text()
env = re.sub(r'ALLOW_TRANSCRIPTION_API=true', 'ALLOW_TRANSCRIPTION_API=false', env)
pathlib.Path('.env').write_text(env)
print('ALLOW_TRANSCRIPTION_API=false に戻しました')
"

# 確認
python scripts/test_cloudflare_transcription_credentials.py
```

## 6. 失敗時のリトライ方針

| エラー | 対応 |
|--------|------|
| 認証エラー (401/403) | CLOUDFLARE_API_TOKEN を再確認・再生成 |
| レート制限 (429) | 10分待ってリトライ。ALLOW_TRANSCRIPTION_API=false に戻す |
| ファイルサイズ超過 | 音声ファイルを30秒以内に切り詰める |
| タイムアウト | --timeout を延ばす。ネットワーク確認 |
| 文字起こし結果が空 | 音声品質を確認。有音の音声ファイルを使用する |

ステータス: `RETRY_WAITING` で記録し、原因解消後に再実行。

## 7. 実行ログの確認方法

```bash
# ログファイルの確認（存在する場合）
ls -la logs/
cat logs/transcription_*.log

# Sheetsのlogsタブで確認
python scripts/check_pipeline_integrity.py --account-id night_scout

# 処理済み分数の確認
grep -i "processed_minutes\|transcription" logs/*.log 2>/dev/null || echo "ログなし"
```

## 関連ファイル

- `scripts/test_cloudflare_transcription_credentials.py` - 認証情報確認
- `scripts/test_cloudflare_transcription_smoke.py` - smoke test実行
- `docs/cloudflare-transcription-setup.md` - 初期設定
- `docs/cloudflare-transcription-smoke-test.md` - smoke test手順詳細
