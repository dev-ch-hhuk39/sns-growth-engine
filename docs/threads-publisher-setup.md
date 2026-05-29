# Threads Publisher 実装手順（Phase 3-E 向け）

Phase 3-E で Threads API を使った本番投稿を実装するための手順書。
**現在（Phase 3-C）は本番投稿しない。**

---

## 現状（Phase 3-C）

`src/publishers/threads_publisher.py` はスタブ実装。

- `dry_run=True` → DryRunPublisher 相当の検証のみ
- `dry_run=False` → `SAFETY_STOP` または `NotImplementedError` で停止
- factory.py は ThreadsPublisher を返さない（コメントアウト済み）

---

## Phase 3-E での実装手順

### 1. Threads API の投稿フロー

Threads API v1.0 はツーステップ方式:

```
Step 1: メディアコンテナを作成
POST https://graph.threads.net/v1.0/{user_id}/threads
  → container_id を取得

Step 2: コンテナを公開
POST https://graph.threads.net/v1.0/{user_id}/threads_publish
  → 投稿 ID を取得
```

### 2. threads_publisher.py の実装

`src/publishers/threads_publisher.py` の `publish()` 内、
`NotImplementedError` の部分に実装を追加する。

```python
# Phase 3-E で実装する箇所
import requests

creds = get_threads_credentials()
access_token = creds["access_token"]
user_id = creds["user_id"]
api_version = creds["api_version"]
base_url = f"https://graph.threads.net/{api_version}"

# Step 1: コンテナ作成
r1 = requests.post(
    f"{base_url}/{user_id}/threads",
    params={
        "media_type": "TEXT",
        "text": text,
        "access_token": access_token,
    },
)
r1.raise_for_status()
container_id = r1.json()["id"]

# Step 2: 公開
import time; time.sleep(5)  # API 推奨の待機
r2 = requests.post(
    f"{base_url}/{user_id}/threads_publish",
    params={
        "creation_id": container_id,
        "access_token": access_token,
    },
)
r2.raise_for_status()
post_id = r2.json()["id"]
posted_url = f"https://www.threads.net/@{account.get('threads_handle','')}/post/{post_id}"
```

### 3. factory.py のコメントアウトを外す

```python
# Phase 3-E でコメントを外す:
# elif plat == "threads":
#     from publishers.threads_publisher import ThreadsPublisher
#     return ThreadsPublisher()
```

### 4. .env の更新

```
PUBLISH_ENABLED=true              ← Phase 3-E のテスト時のみ
ALLOW_REAL_THREADS_POST=true      ← Phase 3-E の手動1件テスト時のみ
THREADS_ACCESS_TOKEN=...
THREADS_USER_ID=...
```

### 5. Phase 3-E の1件手動投稿テスト

```bash
python scripts/check_publisher_credentials.py --platform threads
python scripts/review_queue.py --account-id night_scout --status READY
python scripts/publish_queue.py \
  --account-id night_scout \
  --platform threads \
  --status READY \
  --limit 1
```

---

## 投稿フォーマット推奨

```
フック（1行）
←空行→
本文（複数行可）
```

例:
```
スカウト代理店の稼ぎ方、ロジックで語る。

「個人でやれ」と言われ続けてきたスカウト業界で、
組織化を選んだ代理店の話を聞いてください。
```

DryRunPublisher は空行なしを WARN として検出する。

---

## Threads API アクセストークン有効期限

| トークン種別 | 有効期限 |
|---|---|
| 短期トークン | 1時間 |
| 長期トークン | 60日（延長可能） |

長期トークンは `/refresh_access_token` API で延長できる。
定期的なトークン更新処理（月次等）を Phase 3-E 以降で実装する。

---

## Threads API 文字数・メディア制限

| 種別 | 制限 |
|---|---|
| テキスト | 500文字 |
| 画像 | 1枚（JPEG/PNG） |
| 動画 | 5分以内 |

Phase 3 では テキストのみ投稿を実装する（画像・動画は対象外）。
