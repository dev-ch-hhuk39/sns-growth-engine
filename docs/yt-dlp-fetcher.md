# yt-dlp Fetcher

## 概要

`YtDlpFetcher` は YouTube / TikTok / Instagram などの動画情報を  
`yt-dlp` CLI を使ってローカルで取得するアダプターです。

実際の動画ダウンロードは `--confirm-download` ゲートで保護されており、  
デフォルトでは **メタデータ取得のみ**（`--no-download`）で動作します。

---

## 対象プラットフォーム

| プラットフォーム | collection_method |
|---|---|
| YouTube チャンネル / プレイリスト | `yt_dlp` |
| YouTube 個別動画 | `yt_dlp` |

> TikTok は `tiktok_to_ytdlp` アダプターを使用（`docs/tiktok-to-ytdlp-fetcher.md` 参照）

---

## 必要ツール

```bash
pip3 install yt-dlp
yt-dlp --version  # 確認
```

ツールが未インストールの場合、FetchResult.status = `NOT_INSTALLED` になります（FAILではなくWARN扱い）。

---

## 基本動作

```python
from src.reference.fetchers.yt_dlp_fetcher import YtDlpFetcher

fetcher = YtDlpFetcher()
result = fetcher.fetch(
    source={
        "source_id": "src_ns_yt_001",
        "url": "https://www.youtube.com/@channel_name",
        "max_items_per_run": 5,
        "min_likes": 100,
    },
    dry_run=True,           # デフォルト: メタデータのみ
    confirm_fetch=False,    # False=BLOCKED
)
print(result.status)  # BLOCKED or OK
```

---

## confirm ゲート

| ゲート | 説明 |
|---|---|
| `confirm_fetch=True` | yt-dlp メタデータ取得を許可 |
| `confirm_download=True` | 動画ファイル本体のダウンロードを許可 |

`confirm_fetch=False` の場合: `FetchResult.status = BLOCKED`  
`confirm_download=False` の場合: 動画ファイルDLをスキップし、メタデータのみ返却

---

## RawSourceItem フィールド（yt-dlp 固有）

| フィールド | 説明 |
|---|---|
| `raw_item_id` | YouTube video ID (例: `dQw4w9WgXcQ`) |
| `source_url` | `https://www.youtube.com/watch?v=...` |
| `title` | 動画タイトル |
| `description` | 動画説明文 |
| `published_at` | 投稿日時 (ISO 8601) |
| `duration_sec` | 動画長（秒） |
| `view_count` | 再生数 |
| `like_count` | いいね数 |
| `comment_count` | コメント数 |
| `channel_id` | YouTube チャンネルID |
| `channel_name` | チャンネル名 |
| `thumbnail_url` | サムネイルURL |
| `transcript_available` | 字幕ありフラグ |
| `adapter` | `"yt_dlp"` |

---

## CLI 例

```bash
# dry-run (BLOCKEDを確認)
python3 scripts/fetch_sources.py --source-id src_ns_yt_001 --dry-run

# confirm-fetch (メタデータ取得)
python3 scripts/fetch_sources.py --source-id src_ns_yt_001 --confirm-fetch

# confirm-download (動画DL付き)
python3 scripts/fetch_sources.py --source-id src_ns_yt_001 --confirm-fetch --confirm-download
```

---

## 制約・注意事項

- 大量取得は YouTube 利用規約に注意
- Cookie が必要なソースは `requires_cookie=true` フラグを立てる
- `min_likes` フィルターはメタデータ取得後にローカルで適用
- レート制限回避のため `max_items_per_run` を 10 以下に設定することを推奨

---

## 関連

- `src/reference/fetchers/yt_dlp_fetcher.py`
- `docs/source-fetcher-adapters.md`
- `docs/source-fetcher-tool-selection.md`
