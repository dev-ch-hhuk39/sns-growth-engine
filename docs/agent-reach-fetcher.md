# Agent-Reach Fetcher

## 概要

`AgentReachFetcher` は X（旧 Twitter）のタイムライン / プロフィール情報を  
`Agent-Reach` ツール経由で取得するアダプターです。

X 公式 API は**使用しません**。  
ローカルブラウザセッションを使用するため、`requires_local_login=true` が必要です。

---

## 対象プラットフォーム

| プラットフォーム | collection_method |
|---|---|
| X アカウントタイムライン | `agent_reach` |
| X プロフィール情報 | `agent_reach` |

---

## 必要ツール

`Agent-Reach` は別途インストールが必要です。  
詳細は `docs/source-fetcher-installation.md` を参照してください。

ツールが未インストールの場合: `FetchResult.status = NOT_INSTALLED`

---

## 基本動作

```python
from src.reference.fetchers.agent_reach_fetcher import AgentReachFetcher

fetcher = AgentReachFetcher()
result = fetcher.fetch(
    source={
        "source_id": "src_ns_x_001",
        "url": "https://x.com/account_name",
        "max_items_per_run": 10,
        "requires_local_login": True,
    },
    dry_run=True,
    confirm_fetch=False,  # False=BLOCKED
)
```

---

## ローカルログイン要件

X はブラウザセッションが必要なため、事前に以下を実行してください：

1. ブラウザで X にログイン状態を維持
2. `Agent-Reach` の storage-state を設定
3. `requires_local_login=true` のソースのみ対象とする

---

## confirm ゲート

| ゲート | 説明 |
|---|---|
| `confirm_fetch=True` | X タイムライン取得を許可 |

`confirm_fetch=False` → `FetchResult.status = BLOCKED`

---

## RawSourceItem フィールド（X 固有）

| フィールド | 説明 |
|---|---|
| `raw_item_id` | ツイート / ポスト ID |
| `source_url` | `https://x.com/user/status/...` |
| `title` | ポスト本文（最大 280 文字） |
| `published_at` | 投稿日時 |
| `like_count` | いいね数 |
| `retweet_count` | RT 数 |
| `reply_count` | 返信数 |
| `quote_count` | 引用数 |
| `view_count` | インプレッション数（取得可能な場合） |
| `author_name` | 投稿者アカウント名 |
| `has_media` | メディア添付フラグ |
| `media_urls` | メディアURL一覧 |
| `adapter` | `"agent_reach"` |

---

## 制約・注意事項

- X 利用規約により、大量取得・スクレイピングは禁止
- `max_items_per_run` は 10 以下を推奨
- ログイン状態が切れている場合は `NOT_READY` を返す
- 機密情報（storage-state, cookie）はGitに含めないこと

---

## 関連

- `src/reference/fetchers/agent_reach_fetcher.py`
- `docs/source-fetcher-adapters.md`
- `docs/source-fetcher-installation.md`
