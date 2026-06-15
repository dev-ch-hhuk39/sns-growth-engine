# Last30Days Fetcher

## 概要

`Last30DaysFetcher` は `last30days-skill` を使って  
指定クエリ・ハッシュタグのトレンド情報を取得するアダプターです。

SNS のトレンドワードや急上昇コンテンツを定期的に収集し、  
生成コンテンツの話題選定に活用します。

---

## 対象ユースケース

| ユースケース | 説明 |
|---|---|
| トレンドキーワード収集 | X / Threads のバズワードを収集 |
| ハッシュタグ分析 | 急上昇ハッシュタグの投稿傾向を把握 |
| クエリベース収集 | `query_terms` で指定した検索クエリを実行 |

---

## 必要ツール

`last30days-skill` が利用可能な環境が必要です。  
詳細は `docs/source-fetcher-installation.md` を参照してください。

---

## 基本動作

```python
from src.reference.fetchers.last30days_fetcher import Last30DaysFetcher

fetcher = Last30DaysFetcher()
result = fetcher.fetch(
    source={
        "source_id": "src_ns_trend_001",
        "query_terms": ["ライバー", "Vtuber", "配信 切り抜き"],
        "max_items_per_run": 20,
        "min_likes": 50,
        "language": "ja",
        "region": "JP",
    },
    dry_run=True,
    confirm_fetch=False,
)
```

---

## query_terms フィールド

`query_terms` は配列で複数のクエリを指定できます。

```json
{
  "source_id": "src_ns_trend_001",
  "collection_method": "last30days_skill",
  "query_terms": [
    "ライバー 切り抜き",
    "Vtuber バズ",
    "#ライバー事務所"
  ]
}
```

各クエリは独立して実行され、結果が統合されます。  
重複アイテムは `raw_item_id` で除去されます。

---

## RawSourceItem フィールド（last30days 固有）

| フィールド | 説明 |
|---|---|
| `raw_item_id` | ツイート/ポストID（プラットフォーム依存） |
| `source_url` | コンテンツURL |
| `title` | 本文テキスト |
| `published_at` | 投稿日時 |
| `like_count` | いいね数 |
| `retweet_count` | RT / シェア数 |
| `view_count` | インプレッション数（取得可能な場合） |
| `matched_query` | マッチしたクエリ文字列 |
| `platform` | `"x"` / `"threads"` 等 |
| `adapter` | `"last30days_skill"` |

---

## confirm ゲート

| ゲート | 説明 |
|---|---|
| `confirm_fetch=True` | トレンド取得を許可 |

`confirm_fetch=False` → `FetchResult.status = BLOCKED`

---

## 関連

- `src/reference/fetchers/last30days_fetcher.py`
- `docs/source-fetcher-adapters.md`
- `docs/buzz-scoring.md`
