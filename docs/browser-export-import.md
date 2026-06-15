# Browser Export / Import

## 概要

`BrowserExportFetcher` は、ブラウザで手動収集した SNS コンテンツを  
JSON / CSV ファイルとしてインポートするアダプターです。

API が使えない・スクレイピングが規約違反になる場合の**安全な代替手段**です。

---

## ユースケース

| ケース | 説明 |
|---|---|
| X ポスト手動収集 | ブラウザで閲覧したポストを手動 JSON に保存 |
| Threads コンテンツ収集 | ブラウザエクスポート形式をインポート |
| note 記事収集 | 手動取得した記事データを投入 |
| 過去データ移行 | 既存スプレッドシートからの一括インポート |

---

## 対応フォーマット

### JSON 形式

```json
[
  {
    "id": "1234567890",
    "url": "https://x.com/user/status/1234567890",
    "text": "投稿本文",
    "like_count": 500,
    "retweet_count": 100,
    "published_at": "2025-06-01T12:00:00Z",
    "author": "account_name"
  }
]
```

### CSV 形式

```csv
id,url,text,like_count,retweet_count,published_at,author
1234567890,https://x.com/...,投稿本文,500,100,2025-06-01T12:00:00Z,account_name
```

---

## 基本動作

```python
from src.reference.fetchers.browser_export_fetcher import BrowserExportFetcher

fetcher = BrowserExportFetcher()
result = fetcher.fetch(
    source={
        "source_id": "src_ns_x_manual_001",
        "import_file": "data/manual_exports/night_scout_x_export.json",
        "import_format": "json",
    },
    dry_run=True,
    confirm_fetch=True,  # ローカルファイル読み込みのためconfirmは緩め
)
```

---

## confirm ゲート

| ゲート | 説明 |
|---|---|
| `confirm_fetch=True` | ローカルファイルの読み込みを許可 |

ローカルファイル読み込みのみのため、`confirm_fetch=True` でも安全です。

---

## インポートファイルの配置場所

```
data/
  manual_exports/
    night_scout_x_export.json
    liver_manager_note_export.json
```

`data/manual_exports/` は `.gitignore` に追加してください（個人情報が含まれる場合）。

---

## RawSourceItem フィールド（browser_export 固有）

| フィールド | 説明 |
|---|---|
| `raw_item_id` | インポートデータの `id` フィールド |
| `source_url` | `url` フィールド |
| `title` | `text` フィールド |
| `published_at` | `published_at` フィールド |
| `like_count` | `like_count` フィールド |
| `import_source_file` | インポート元ファイルパス |
| `adapter` | `"browser_export"` |

---

## フィールドマッピング設定

CSV など列名が異なる場合はフィールドマッピングを設定します：

```json
{
  "source_id": "src_ns_x_manual_001",
  "collection_method": "browser_export",
  "import_file": "data/manual_exports/export.csv",
  "import_format": "csv",
  "field_mapping": {
    "id": "tweet_id",
    "text": "content",
    "like_count": "likes"
  }
}
```

---

## 関連

- `src/reference/fetchers/browser_export_fetcher.py`
- `docs/source-fetcher-adapters.md`
