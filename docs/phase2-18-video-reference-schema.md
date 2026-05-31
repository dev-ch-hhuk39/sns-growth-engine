# Phase 2.18 — 動画 reference スキーマ拡張

**実装日**: 2026-05-31  
**ステータス**: 完了

---

## 背景

Phase 2.10〜2.11 で X 投稿の reference pipeline を構築した。  
Phase 2.18〜2.20 では YouTube/TikTok 動画を参考投稿として取り込み、  
文字起こし → クリップ候補抽出 → SNS 投稿生成の基盤を構築する。

---

## 追加タブ

### reference_sources

YouTube/TikTok の収集元チャンネル・アカウントを管理する。  
単発URL処理ではなく、source_id ベースで収集対象を一元管理する。

| 列 | 説明 |
|---|---|
| source_id | `src-{account_id}-{platform}-{handle}` 形式 |
| account_id | night_scout / liver_manager |
| platform | youtube / tiktok |
| source_url | チャンネルURL / プロフィールURL |
| handle | ハンドル名（@なし） |
| priority | 収集優先度（1=高〜10=低、デフォルト5） |
| active | TRUE/FALSE |
| collection_frequency | daily / weekly / manual |
| last_collected_at | 最終収集日時 |

### video_transcripts

Cloudflare Whisper の文字起こし結果を保存する。  
transcript_id でアップサート（同じ動画を再処理しても安全）。

| 列 | 説明 |
|---|---|
| transcript_id | `tr-{uuid8}` |
| reference_post_id | reference_posts の id と紐づく |
| transcription_status | pending / processing / done / failed / skipped |
| duration_seconds | 動画長（秒）、上限計算に使用 |
| transcript_text | 文字起こし全文 |
| segments_json | word-level タイムスタンプ（JSON文字列） |
| processed_minutes | 消費した文字起こし時間（分） |

### video_clip_candidates

文字起こしから抽出したクリップ候補。将来の ffmpeg 切り抜き・Cloudinary 保存に使う。

| 列 | 説明 |
|---|---|
| clip_id | `clip-{uuid8}` |
| start_time / end_time | クリップ区間（秒） |
| hook | 冒頭フック文 |
| x_post_angle / threads_post_angle | 各プラットフォーム向け投稿方向性 |
| clip_status | candidate / approved / rejected |
| rights_status / permission_status | 権利確認状態（初期値: unknown） |

### transcription_runs

1日の文字起こし実行記録。120分/日の上限管理に使う。  
TranscriptionLimiter が起動時に読み込み、終了時に1回書き戻す。

---

## reference_posts 追加列

| 列 | 説明 |
|---|---|
| content_type | video / text / image |
| video_id | プラットフォーム固有の動画ID |
| video_url | 動画URL |
| creator_handle | 投稿者ハンドル（YouTubeチャンネル等） |
| channel_id / channel_name | チャンネル情報 |
| description | 動画説明文（最大500文字） |
| duration_seconds | 動画長（秒） |
| thumbnail_url | サムネイルURL |
| comment_count | コメント数 |
| raw_payload_json | API生レスポンス（JSON文字列、2000文字上限） |
| transcription_status | pending → done/failed |
| clip_generation_status | pending → done/failed |

---

## 既存データへの影響

- _ensure_tab() の冪等設計により、既存列は変更しない
- 新列は右端に追加されるのみ（既存データ破壊なし）
