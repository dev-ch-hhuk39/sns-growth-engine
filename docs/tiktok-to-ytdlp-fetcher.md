# TikTok → yt-dlp Fetcher

## 概要

`TikTokToYtdlpFetcher` は TikTok の動画情報を `yt-dlp` 経由で取得するアダプターです。  
TikTok 公式 API は使用しません。

> **重要:** TikTok コンテンツの取得はローカル認証（Cookie）が必要になる場合があります。  
> `requires_cookie=true` のソースはブラウザエクスポートした Cookie ファイルを事前に配置してください。

---

## 対象プラットフォーム

| プラットフォーム | collection_method |
|---|---|
| TikTok アカウント動画 | `tiktok_to_ytdlp` |
| TikTok ハッシュタグ | `tiktok_to_ytdlp`（制限あり） |

---

## 必要ツール

```bash
pip3 install yt-dlp
yt-dlp --version
```

---

## 基本動作

```python
from src.reference.fetchers.tiktok_to_ytdlp_fetcher import TikTokToYtdlpFetcher

fetcher = TikTokToYtdlpFetcher()
result = fetcher.fetch(
    source={
        "source_id": "src_ba_tiktok_001",
        "url": "https://www.tiktok.com/@account_name",
        "max_items_per_run": 5,
        "requires_cookie": True,
        "cookie_file": "config/cookies/tiktok_cookies.txt",
    },
    dry_run=True,
    confirm_fetch=False,
)
```

---

## Cookie 設定

TikTok は認証が必要なコンテンツがあります。

1. ブラウザ拡張（`Get cookies.txt LOCALLY` など）でエクスポート
2. `config/cookies/tiktok_cookies.txt` に保存
3. ソース設定に `"requires_cookie": true, "cookie_file": "config/cookies/tiktok_cookies.txt"` を追加

Cookie ファイルは **`.gitignore` に必ず追加**してください。

---

## confirm ゲート

| ゲート | 説明 |
|---|---|
| `confirm_fetch=True` | TikTok メタデータ取得を許可 |
| `confirm_download=True` | 動画ファイル本体のダウンロードを許可 |

---

## RawSourceItem フィールド（TikTok 固有）

| フィールド | 説明 |
|---|---|
| `raw_item_id` | TikTok 動画ID |
| `source_url` | TikTok 動画URL |
| `title` | 動画タイトル / キャプション |
| `published_at` | 投稿日時 |
| `duration_sec` | 動画長（秒） |
| `view_count` | 再生数 |
| `like_count` | いいね数 |
| `share_count` | シェア数 |
| `comment_count` | コメント数 |
| `author_name` | 投稿者アカウント名 |
| `hashtags` | ハッシュタグ一覧 |
| `thumbnail_url` | サムネイルURL |
| `adapter` | `"tiktok_to_ytdlp"` |

---

## beauty_account における TikTok ソース

`beauty_account` の TikTok ソース候補は `candidate_status=candidate` で登録されており、  
`fetch_enabled=false` がデフォルトです。

運用開始前に以下を確認してください：
- `docs/beauty-account-activation-checklist.md`
- `subject_policy.female_subject_required=true`（女性被写体のみ使用可）
- `subject_policy.no_male_scout_talking_head_for_clip=true`

---

## 関連

- `src/reference/fetchers/tiktok_to_ytdlp_fetcher.py`
- `docs/source-fetcher-adapters.md`
- `docs/yt-dlp-fetcher.md`
