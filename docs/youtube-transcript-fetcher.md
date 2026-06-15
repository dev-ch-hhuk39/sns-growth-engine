# YouTube Transcript Fetcher

## 概要

`YoutubeTranscriptFetcher` は `youtube-transcript-api` ライブラリを使って  
YouTube 動画の字幕（トランスクリプト）を取得するアダプターです。

動画内容を文字起こしして生成コンテンツの素材として活用します。  
yt-dlp との違いは、**動画ファイルをダウンロードせずテキストのみを取得**できる点です。

---

## 必要ツール

```bash
pip3 install youtube-transcript-api
```

ツールが未インストールの場合: `FetchResult.status = NOT_INSTALLED`

---

## 基本動作

```python
from src.reference.fetchers.youtube_transcript_fetcher import YoutubeTranscriptFetcher

fetcher = YoutubeTranscriptFetcher()
result = fetcher.fetch(
    source={
        "source_id": "src_lm_yt_001",
        "url": "https://www.youtube.com/@channel_name",
        "max_items_per_run": 5,
        "language": "ja",
        "transcript_required": True,
    },
    dry_run=True,
    confirm_fetch=False,
)
```

---

## transcript_required フラグ

`transcript_required=true` のソースは、字幕が存在しない動画をスキップします。  
`transcript_required=false` のソースは、字幕なし動画もメタデータのみで返却します。

---

## confirm ゲート

| ゲート | 説明 |
|---|---|
| `confirm_fetch=True` | トランスクリプト取得を許可 |

`confirm_fetch=False` → `FetchResult.status = BLOCKED`  
**動画ファイルのダウンロードは行いません。**

---

## RawSourceItem フィールド（transcript 固有）

| フィールド | 説明 |
|---|---|
| `raw_item_id` | YouTube video ID |
| `source_url` | `https://www.youtube.com/watch?v=...` |
| `title` | 動画タイトル |
| `description` | 動画説明文 |
| `published_at` | 投稿日時 |
| `duration_sec` | 動画長（秒） |
| `view_count` | 再生数 |
| `like_count` | いいね数 |
| `transcript_text` | 字幕全文テキスト（区切り付き） |
| `transcript_language` | 字幕言語コード（例: `"ja"`, `"en"`） |
| `transcript_segments` | タイムスタンプ付きセグメント配列 |
| `adapter` | `"youtube_transcript"` |

---

## liver_manager における活用例

`liver_manager` の YouTube ソースでは `transcript_required=true` に設定し、  
トランスクリプトから切り抜き素材候補を特定するパイプラインに使います。

```json
{
  "source_id": "src_lm_yt_001",
  "collection_method": "youtube_transcript",
  "transcript_required": true,
  "target_generation_modes": ["clip_reference", "thread_from_transcript"]
}
```

---

## 制約・注意事項

- 自動生成字幕（Auto-generated）は精度が低い場合があります
- 手動字幕がある動画を優先する場合は `prefer_manual_transcript=true` を設定
- 字幕が存在しない動画は `NOT_READY` を返します（FAILではありません）

---

## 関連

- `src/reference/fetchers/youtube_transcript_fetcher.py`
- `docs/yt-dlp-fetcher.md`
- `docs/source-fetcher-adapters.md`
