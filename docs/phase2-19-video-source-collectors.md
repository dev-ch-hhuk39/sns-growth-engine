# Phase 2.19 — 動画収集アダプター基盤

**実装日**: 2026-05-31  
**ステータス**: 完了

---

## 概要

YouTube / TikTok の動画メタデータを収集し、reference_posts タブに保存する基盤。  
**実際の API 呼び出しは行わない**（mock / JSON ファイル入力のみで全テストが通る）。

---

## モジュール構成

```
src/collectors/
  video_source_manager.py      ソース定義の CRUD（reference_sources タブ）
  youtube_video_collector.py   YouTube 動画正規化アダプター
  tiktok_video_collector.py    TikTok 動画正規化アダプター
```

---

## video_source_manager.py

`reference_sources` タブの管理。

| 関数 | 役割 |
|---|---|
| `build_source_id(account_id, platform, handle)` | 決定論的なソースID生成 |
| `normalize_source(raw)` | ソース定義の正規化 |
| `get_active_sources(client, account_id, platform)` | アクティブなソース一覧（優先度順） |
| `register_source(client, source_def, dry_run)` | ソースを reference_sources に登録 |
| `mark_source_collected(client, source_id, dry_run)` | last_collected_at を更新 |

---

## normalized_video_reference フォーマット

YouTube / TikTok どちらも同じ `reference_posts` 行フォーマットに変換する。

```python
{
    "id": "ref-yt-xxx",
    "account_id": "night_scout",
    "platform": "youtube",          # youtube / tiktok
    "content_type": "video",        # 動画の識別キー
    "video_id": "yt_xxxxx",
    "video_url": "https://...",
    "creator_handle": "channel_handle",
    "channel_id": "UCxxxxx",
    "channel_name": "チャンネル名",
    "title": "動画タイトル",
    "description": "説明文（500文字以内）",
    "duration_seconds": 480,
    "thumbnail_url": "https://...",
    "likes": 3200,
    "reposts": 0,
    "impressions": 85000,
    "comment_count": 142,
    "published_at": "2026-04-15T12:00:00Z",
    "raw_payload_json": "...",
    "transcription_status": "pending",
    "clip_generation_status": "pending",
    "status": "ACTIVE",
}
```

---

## 設計判断

- **実 API は未実装**: TikTok 公式 API は審査が厳格で未取得。YouTube Data API も quota 管理が必要。現時点は mock/JSON 入力のみ。
- **content_type=video でフィルタ**: 文字起こし対象を `content_type=video` の reference_posts に限定。X テキスト投稿と混在しても安全。
- **IDは "ref-yt-" / "ref-tk-" プレフィックス**: post_id との区別が視覚的に明確。
- **raw_payload_json は2000文字上限**: Sheets セル上限（50000文字）より小さく絞ることで安全。
