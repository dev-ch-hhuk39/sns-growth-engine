# YouTube / TikTok / Cloudinary / Clip Pipeline Runbook

実download・cut・uploadはまだ実行しない。
ユーザーが source URL と権利確認を入力した後、このドキュメントの手順で一発で進められる。

---

## Source Registry 現在の状態 (2026-06-23)

| source_id | 状態 | rights_policy | URL |
|---|---|---|---|
| src_ns_x_cand_001 | READY_FOR_REFERENCE_FETCH | reference_only | https://x.com/takashimaanna |
| src_ns_yt_cand_001 | WAITING_RIGHTS_REVIEW | unknown | YouTube channel |
| src_lm_yt_cand_001 | WAITING_RIGHTS_REVIEW | unknown | YouTube @suu-san_pococha |
| src_lm_note_cand_001 | READY_FOR_REFERENCE_FETCH | reference_only | note.com |
| src_ba_yt_cand_001 | BLOCKED_BEAUTY_ACCOUNT | — | 永続ブロック |
| src_ba_tt_cand_001 | BLOCKED_BEAUTY_ACCOUNT | — | 永続ブロック |
| src_ba_x_cand_001 | BLOCKED_BEAUTY_ACCOUNT | — | 永続ブロック |
| src_ns_query_001 | WAITING_URL_INPUT | reference_only | URL未登録 |

### 次にユーザーが入力すべきもの

**1. src_ns_query_001 — URL登録**

```yaml
account_id: night_scout
source_platform: youtube  # または x / tiktok / note
source_url: <URL を入力>
source_handle: <@handle または channel_id>
purpose: テキスト参照 / コンテンツ分析
rights_policy: reference_only  # または approved_media
reuse_policy: reference_only
media_policy: do_not_download  # または approved_media_only
can_fetch: false  # active化後に true に変更
can_download: false
can_clip: false
can_upload: false
notes: <登録理由・確認内容>
```

**2. src_ns_yt_cand_001 / src_lm_yt_cand_001 — 権利確認**

```yaml
# 確認項目:
# - 商用利用禁止の明示があるか
# - 切り抜き転載の可否
# - 利用規約で参照のみ許可か

# 確認後、default_sources.json を更新:
rights_policy: <reference_only | approved_media | do_not_use>
reuse_policy:  <reference_only | approved_media>
media_policy:  <do_not_download | approved_media_only>
```

---

## 実fetch / transcript / clip の実行条件と手順

### 前提条件チェックリスト

```
□ rights_policy が reference_only / approved_media / own_media のいずれか
□ candidate_status = approved
□ active = true (fetch_enabled = true)
□ allow_network_fetch = true (fetch時のみ)
□ allow_download = true (download時のみ) → approved_media / own_media のみ
□ allow_cut = true (cut時のみ) → approved_media / own_media のみ
□ allow_upload = true (upload時のみ) → ALLOW_CLOUDINARY_UPLOAD=true 必須
```

### Step 1: Source を active 化（権利確認後のみ）

```bash
# default_sources.json を編集して active/fetch_enabled を true に変更後:
python3 scripts/test_source_intake_schema.py  # schema 検証
python3 scripts/test_media_policy_guard.py     # policy guard 確認
```

### Step 2: 実 fetch（テキスト参照のみ / 実 download なし）

```bash
# reference_only ソース向け（テキスト参照のみ）
python3 scripts/fetch_source_posts.py \
  --account-id night_scout \
  --source-id src_ns_x_cand_001 \
  --dry-run  # まず dry-run で確認

# 確認後、dry-run 外す場合は --no-dry-run を指定
# ※ allow_network_fetch=true が必要
```

### Step 3: Transcript 取得（approved_media のみ）

```bash
# ALLOW_TRANSCRIPTION_API=true 設定が必要
# ※ 現在は実行禁止（本番準備完了後に解除）
ALLOW_TRANSCRIPTION_API=true python3 scripts/fetch_video_transcript.py \
  --source-id <source_id> \
  --video-id <youtube_video_id> \
  --dry-run
```

### Step 4: Clip candidate 生成（plan_only まで）

```bash
# 実 download はしない。計画のみ生成。
python3 scripts/preflight_media_assets.py \
  --account-id night_scout \
  --mock --dry-run
```

### Step 5: 実 download（approved_media のみ）

```bash
# 実行条件:
# - allow_download=true
# - rights_policy=approved_media または own_media
# - ALLOW_TRANSCRIPTION_API=true (transcript付きの場合)
# ※ 現在は実行禁止

python3 scripts/download_video_clips.py \
  --source-id <source_id> \
  --video-id <video_id> \
  --confirm-download  # 必須フラグ
```

### Step 6: 実 cut（approved_media のみ）

```bash
# 実行条件:
# - allow_cut=true
# - rights_policy=approved_media または own_media
# ※ 現在は実行禁止

python3 scripts/cut_video_clips.py \
  --asset-id <asset_id> \
  --confirm-cut  # 必須フラグ
```

### Step 7: Cloudinary upload（approved_media のみ）

```bash
# 実行条件:
# - ALLOW_CLOUDINARY_UPLOAD=true
# - allow_upload=true
# - rights_policy=approved_media または own_media
# ※ 現在は実行禁止

ALLOW_CLOUDINARY_UPLOAD=true python3 scripts/upload_to_cloudinary.py \
  --asset-id <asset_id> \
  --confirm-upload  # 必須フラグ
```

### Step 8: メディア付き投稿に進む条件

```
□ post_media_url が Cloudinary に存在する
□ media_policy=approved_media_only
□ candidate_status=approved
□ rights_policy=approved_media または own_media
□ PUBLISH_ENABLED=true
□ ALLOW_REAL_THREADS_POST=true または ALLOW_REAL_X_POST=true
□ X の場合: X API 課金プランが有効（402 解消済み）
```

---

## 現在の制約（変更禁止）

| 項目 | 状態 | 解除条件 |
|---|---|---|
| 実 download | 禁止 | rights_policy 確認 + allow_download=true |
| 実 cut | 禁止 | 同上 + allow_cut=true |
| Cloudinary upload | 禁止 | ALLOW_CLOUDINARY_UPLOAD=true + approved_media |
| transcription API | 禁止 | ALLOW_TRANSCRIPTION_API=true + 明示承認 |
| beauty_account | 永続禁止 | 解除不可 |
| auto_priority_change | 禁止 | auto_priority_change_allowed=false |
