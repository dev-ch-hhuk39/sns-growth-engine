# Manual Smoke Test Sequence

実テストを安全に1ステップずつ実行するための手順書。
**必ず順番通りに実行すること。**

## 前提確認

```bash
cd /Users/hayatoa/claudecodeプロジェクトディレクトリ/dev/SNS自動投稿システム/v2
python scripts/run_real_smoke_plan.py --step all --account-id night_scout
```

全ステップが `READY_FOR_MANUAL_SMOKE` 以上になっていること。

---

## Step 1: Cloudflare 30秒 Transcription テスト

### 前提
- `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN` 設定済み
- 30秒以内の音声ファイルが存在する

### 手順

```bash
# 1-1. 認証情報確認（実API不要・常時安全）
python scripts/test_cloudflare_transcription_credentials.py

# 1-2. 音声ファイル準備（ffmpegで30秒音声作成）
ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 30 tests/fixtures/smoke_audio_30s.mp3

# 1-3. .env で ALLOW_TRANSCRIPTION_API=true に変更

# 1-4. smoke test 実行（30秒以内の音声ファイルのみ）
python scripts/test_cloudflare_transcription_smoke.py \
  --audio-file tests/fixtures/smoke_audio_30s.mp3 \
  --use-api \
  --confirm-api

# 1-5. 実行後すぐに false へ戻す（必須）
python -c "
import re, pathlib
env = pathlib.Path('.env').read_text()
env = re.sub(r'ALLOW_TRANSCRIPTION_API=true', 'ALLOW_TRANSCRIPTION_API=false', env)
pathlib.Path('.env').write_text(env)
print('ALLOW_TRANSCRIPTION_API=false に戻しました')
"

# 1-6. 戻し確認
python scripts/test_cloudflare_transcription_credentials.py
```

---

## Step 2: Cloudinary 小ファイル Upload テスト

### 前提
- Cloudinary 認証情報 3項目が設定済み
- 小さいテスト用ファイルがある

### 手順

```bash
# 2-1. 認証情報確認
python scripts/test_cloudinary_credentials.py

# 2-2. テスト用ファイル準備（1x1px PNG）
python -c "
import base64, pathlib
data = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')
pathlib.Path('tests/fixtures/smoke_test_1px.png').write_bytes(data)
print('作成完了')
"

# 2-3. .env で ALLOW_CLOUDINARY_UPLOAD=true に変更

# 2-4. smoke upload 実行（小ファイルのみ）
python scripts/test_cloudinary_upload_smoke.py \
  --file tests/fixtures/smoke_test_1px.png \
  --upload \
  --confirm-upload

# 2-5. アップロードしたファイルを削除
# Cloudinary Dashboard または API で削除

# 2-6. false へ戻す（必須）
python -c "
import re, pathlib
env = pathlib.Path('.env').read_text()
env = re.sub(r'ALLOW_CLOUDINARY_UPLOAD=true', 'ALLOW_CLOUDINARY_UPLOAD=false', env)
pathlib.Path('.env').write_text(env)
print('ALLOW_CLOUDINARY_UPLOAD=false に戻しました')
"
```

---

## Step 3: Video Clip Dry-Run

```bash
# 実ダウンロード・実切り抜きはしない
python scripts/preflight_video_real_test.py --account-id night_scout --mock
python scripts/analyze_video_clips.py --account-id night_scout --dry-run
```

---

## Step 4: X テキストのみ 1件投稿

### 前提
- X API 認証情報 4項目が設定済み
- queue に `status=READY` の候補が存在する
- 投稿テキストが 120文字以内
- `rights_review_required=false`

### 手順

```bash
# 4-1. preflight 確認
python scripts/preflight_x_real_post.py --account-id night_scout

# 4-2. キュー確認・queue_id メモ
python scripts/review_queue.py --account-id night_scout --status READY

# 4-3. .env で PUBLISH_ENABLED=true, ALLOW_REAL_X_POST=true に変更

# 4-4. 1件のみ投稿
python scripts/publish_queue.py \
  --account-id night_scout \
  --queue-id {queue_id} \
  --confirm-real-post \
  --max-real-posts 1

# 4-5. 投稿後すぐに false へ戻す（必須）
python -c "
import re, pathlib
env = pathlib.Path('.env').read_text()
env = re.sub(r'PUBLISH_ENABLED=true', 'PUBLISH_ENABLED=false', env)
env = re.sub(r'ALLOW_REAL_X_POST=true', 'ALLOW_REAL_X_POST=false', env)
pathlib.Path('.env').write_text(env)
print('安全フラグをfalseに戻しました')
"
```

---

## Step 5: X メディア付き 1件投稿

```bash
# Step 4の手順に加えて --with-media を追加
# 事前に Cloudinary へのアップロード完了が必要

python scripts/publish_queue.py \
  --account-id night_scout \
  --queue-id {queue_id} \
  --with-media \
  --confirm-real-post \
  --max-real-posts 1
```

---

## Step 6: 投稿後 false 戻し確認

```bash
python scripts/print_env_status.py
# 全フラグが false であることを確認
```

---

## Step 7: posted_results 確認

```bash
python scripts/check_pipeline_integrity.py --account-id night_scout
```

---

## Step 8: Learning Export / 分析

```bash
# 投稿結果を分析
python scripts/analyze_post_results.py --account-id night_scout

# 改善提案生成（dry-run）
python scripts/generate_learning_from_results.py \
  --account-id night_scout \
  --dry-run
```

---

## Step 9: account_config 安全確認（Phase 6.0）

```bash
# pipeline integrity に account_config チェックが含まれる
python scripts/check_pipeline_integrity.py --mock

# beauty_account は draft_only ブロックを確認
python scripts/preflight_x_real_post.py --account-id beauty_account --mock
# → [BLOCKED] beauty_account は draft_only アカウントです。 が表示されること
```

## Step 10: thread_series 動作確認（Phase 6.2）

```bash
# night_scout dry-run
python scripts/generate_thread_series.py \
  --account-id night_scout --platform x \
  --theme "夜職で稼ぐ方法" --mock-llm

# beauty_account（draft_only アカウント）
python scripts/generate_thread_series.py \
  --account-id beauty_account --platform threads \
  --post-count 5 --mock-llm --test-write

# beauty_account レビュー
python scripts/review_thread_series.py --account-id beauty_account
# → [WARN] draft_only アカウント が表示されること（FAILではない）
```

**beauty_account 禁止事項（厳守）:**
- READY 化禁止
- 実投稿禁止（preflight は BLOCKED で終了する）
- queue.status = POSTED 禁止

