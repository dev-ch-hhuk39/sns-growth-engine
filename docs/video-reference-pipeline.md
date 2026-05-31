# 動画 reference pipeline 設計

**作成日**: 2026-05-31

---

## 全体フロー

```
[YouTube/TikTok チャンネル]
        ↓ 収集（Phase 2.19）
reference_sources（収集元管理）
        ↓
reference_posts（content_type=video）
        ↓ 文字起こし（Phase 2.20）
video_transcripts
        ↓ クリップ候補抽出（Phase 2.20）
video_clip_candidates
        ↓ 動画切り抜き（Phase 3-E以降）
media_assets（Cloudinary）
        ↓ 投稿生成（Phase 2.14〜）
drafts → social_derivatives → queue
```

---

## データフロー

### Step 1: ソース登録

```python
register_source(client, {
    "account_id": "night_scout",
    "platform": "youtube",
    "source_url": "https://www.youtube.com/@channel",
    "handle": "channel_name",
    "priority": 1,
    "active": "TRUE",
    "collection_frequency": "weekly",
})
```

### Step 2: 動画収集（正規化）

```python
# YouTube
refs = collect_from_mock(mock_videos, account_id="night_scout")
save_video_references(client, refs, dry_run=True)

# TikTok
refs = collect_from_json_file("fixtures/sample_video_references.json", account_id="night_scout")
```

### Step 3: 文字起こし

```python
limiter = TranscriptionLimiter(client, limit_minutes=120)
whisper = CloudflareWhisperClient.from_config(cfg, dry_run=True)
if limiter.can_process(duration_seconds):
    result = whisper.transcribe(audio_path, ...)
    limiter.record(duration_seconds, result.status)
limiter.flush()
```

### Step 4: クリップ候補抽出

```python
clips = build_clip_candidates_from_transcripts(transcripts, account_id="night_scout")
for clip in clips:
    client.save_video_clip_candidate(clip)
```

---

## プラットフォーム対応状況

| プラットフォーム | 収集API | 状況 |
|---|---|---|
| YouTube | YouTube Data API v3 | スタブ（mock/JSON入力で動作） |
| TikTok | 未定（公式API審査中） | スタブ（mock/JSON入力で動作） |
| X | tweepy（既実装） | Phase 2.10〜2.11 で完了 |

---

## 制約・設計判断

- **動画ダウンロードしない**: yt-dlp / ffmpeg は使わない（Phase 2.18〜2.20の範囲外）
- **Cloudinary アップロードしない**: ALLOW_CLOUDINARY_UPLOAD=false のまま
- **元動画の比率維持**: 9:16 固定にしない（切り抜き不要 or 将来の Phase で判断）
- **字幕焼き込みは必須にしない**: 動画クリップ単体でも価値がある
- **文字起こし fallback なし**: 失敗したら次回再実行。課金回避優先。
