# 動画クリップ投稿文生成 使用ガイド

**作成日**: 2026-06-04

---

## 全体フロー

```
reference_posts（video）
  ↓ transcribe_videos.py
video_transcripts（done）
  ↓ analyze_video_clips.py
video_clip_candidates（candidate）
  ↓ [人間: rights_status / permission_status 確認・更新]
  ↓ cut_video_clips.py（オプション）
  ↓ generate_from_video_clips.py
drafts（WAITING_REVIEW）
social_derivatives（WAITING_REVIEW）
queue（WAITING_REVIEW）
  ↓ [人間: approve_queue.py]
queue（READY）
  ↓ Phase 3 投稿実行
```

---

## コマンド一覧

### 1. 文字起こし

```bash
# モック動作
python scripts/transcribe_videos.py --account-id night_scout

# 実Sheets 読み込み + 書き込みあり
python scripts/transcribe_videos.py --account-id night_scout --use-sheets --test-write

# 実API（ALLOW_TRANSCRIPTION_API=true 必要）
python scripts/transcribe_videos.py --account-id night_scout --use-sheets --test-write --allow-real-transcription
```

### 2. クリップ候補抽出

```bash
# モック動作
python scripts/analyze_video_clips.py --account-id night_scout

# 実Sheets + mockLLM + 書き込みあり（推奨テスト手順）
python scripts/analyze_video_clips.py --account-id night_scout --use-sheets --test-write --mock-llm

# 実Sheets + 実LLM + 書き込みあり
python scripts/analyze_video_clips.py --account-id night_scout --use-sheets --test-write
```

### 3. クリップ切り抜き（オプション）

```bash
# dry-run（デフォルト）
python scripts/cut_video_clips.py --account-id night_scout --dry-run

# 実Sheets + dry-run + Sheets書き込みあり
python scripts/cut_video_clips.py --account-id night_scout --use-sheets --test-write --dry-run

# 実切り抜き（両フラグ必要）
python scripts/cut_video_clips.py --account-id night_scout --use-sheets --test-write --cut --confirm-cut
```

### 4. 投稿文生成

```bash
# モック動作
python scripts/generate_from_video_clips.py --account-id night_scout

# 実Sheets + mockLLM + 書き込みあり（推奨テスト手順）
python scripts/generate_from_video_clips.py --account-id night_scout --use-sheets --test-write --mock-llm

# 実Sheets + 実LLM + 書き込みあり
python scripts/generate_from_video_clips.py --account-id night_scout --use-sheets --test-write
```

---

## 権利ゲート

`rights_status=unknown` または `not_allowed` または `media_reuse_risk=high` のクリップは自動的に queue に追加されない。

詳細: `docs/video-clip-rights-policy.md`

---

## 生成後のステータス遷移

| 項目 | 値 |
|---|---|
| drafts.status | WAITING_REVIEW |
| social_derivatives.status | WAITING_REVIEW |
| queue.status | WAITING_REVIEW |
| video_clip_candidates.text_generation_status | done |

READY への昇格は `approve_queue.py` による人間レビュー後のみ。

---

## 安全ガード一覧

| ガード | 設定 |
|---|---|
| SNS本番投稿禁止 | PUBLISH_ENABLED=false |
| X API投稿禁止 | ALLOW_REAL_X_POST=false |
| Threads API投稿禁止 | ALLOW_REAL_THREADS_POST=false |
| Cloudinary実アップロード禁止 | ALLOW_CLOUDINARY_UPLOAD=false |
| 実文字起こし禁止 | ALLOW_TRANSCRIPTION_API=false |
| ffmpeg実切り抜き禁止 | --dry-run（デフォルト）|
| 権利未確認クリップの自動投稿禁止 | 権利ゲート（コード実装）|
