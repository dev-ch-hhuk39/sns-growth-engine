# Source Fetcher Adapters（Phase 9）

## 概要

Phase 9 で実装した API なし Source Fetcher アダプター群の一覧と使い方。

すべてのアダプターは `BaseFetcher` を継承し、`fetch()` メソッドを実装する。

## アダプター一覧

| adapter_name | collection_method | 用途 | 実fetch |
|---|---|---|---|
| `manual_json` | manual_json / manual_csv / manual_url | 手動投入ファイル | 不要 |
| `yt_dlp` | yt_dlp | YouTube / TikTok / Shorts メタデータ | yt-dlp CLI |
| `tiktok_to_ytdlp` | tiktok_to_ytdlp | TikTok プロフィール → URL → yt-dlp | tiktok-to-ytdlp CLI |
| `agent_reach` | agent_reach | X / YouTube Agent-Reach | agent-reach CLI |
| `last30days_skill` | last30days_skill | 30日トレンド抽出 | last30days-skill CLI |
| `youtube_transcript` | youtube_transcript | YouTube 文字起こし | youtube-transcript-api |
| `browser_export` | browser_export | ブラウザエクスポートJSON/CSV/MD | ローカルファイル |

## 安全ゲート

すべてのアダプターは以下の条件でブロックされる:

- `confirm_fetch=False`（デフォルト）→ `BLOCKED`
- ツール未インストール → `NOT_INSTALLED`
- scrape_disallowed → `BLOCKED`

## 使い方（mock）

```python
from src.reference.fetchers.fetcher_registry import get_fetcher

fetcher = get_fetcher("yt_dlp")
result = fetcher.fetch(
    source={
        "source_id": "src_001",
        "source_url": "https://www.youtube.com/@example",
        "source_platform": "youtube",
    },
    target_account_id="night_scout",
    max_items=5,
    mock=True,
)
print(result.status)  # OK
print(len(result.items))  # 3
```

## 実 fetch（yt_dlp の場合）

```bash
# --confirm-fetch フラグが必要
python scripts/fetch_source_posts.py \
  --source-id src_ns_yt_001 \
  --adapter yt_dlp \
  --confirm-fetch \
  --max-items 10
```

## RawSourceItem の主要フィールド

| フィールド | 説明 |
|---|---|
| raw_item_id | 一意ID（UUID） |
| source_id | ソースID |
| source_platform | youtube / x / tiktok / threads |
| text | 投稿文 / タイトル / 文字起こし |
| like_count | いいね数 |
| view_count | 視聴数 |
| buzz_score | 0.0〜1.0 正規化スコア |
| why_it_grew | バズ理由テキスト |
| replay_tip | 再現のヒント |
| recommended_generation_mode | reference_based / original_hypothesis / video_reference |

## 注意事項

- `media_policy=plan_only` のソースは動画ダウンロード禁止
- `rights_policy=unknown` は WAITING_REVIEW 必須
- `beauty_account` の生成物は常に WAITING_REVIEW
