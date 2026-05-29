# X Publisher 実装手順（Phase 3-D 実装済み）

Phase 3-D で X API を使った本番投稿の実装が完了した。

---

## 現状（Phase 3-D）

`src/publishers/x_publisher.py` は tweepy OAuth 1.0a による本番投稿実装済み。

- `dry_run=True` → DryRunPublisher 相当の検証のみ（投稿なし）
- `dry_run=False` → 安全ガード通過後に tweepy で実投稿
  1. PUBLISH_ENABLED=true チェック
  2. ALLOW_REAL_X_POST=true チェック
  3. テキスト検証（空・140字超）
  4. 認証情報4項目すべて設定チェック
  5. tweepy.Client.create_tweet() 実行
- `factory.py` は XPublisher を返す（Phase 3-D 有効化済み）

---

## 本番投稿のための手順

詳細は `docs/phase3d-x-manual-post.md` を参照。

### 概要

```bash
# 1. テスト全通過確認
python scripts/test_phase3d.py

# 2. 認証情報確認
python scripts/test_x_credentials.py

# 3. .env に一時設定
#   PUBLISH_ENABLED=true
#   ALLOW_REAL_X_POST=true
#   X_API_KEY=...  (X Developer Portal で取得)
#   X_API_SECRET=...
#   X_ACCESS_TOKEN=...
#   X_ACCESS_TOKEN_SECRET=...

# 4. dry-run で最終確認
python scripts/publish_queue.py \
  --account-id night_scout --platform x --status READY --dry-run

# 5. 1件だけ本番投稿
python scripts/publish_queue.py \
  --account-id night_scout --platform x --status READY --limit 1 \
  --confirm-real-post --queue-id <queue_id> --max-real-posts 1

# 6. .env を元に戻す（必須）
#   PUBLISH_ENABLED=false
#   ALLOW_REAL_X_POST=false
```

---

## requirements.txt への追加（実施済み）

`tweepy>=4.14.0` は `requirements.txt` に追加済み。

---

## X API v2 投稿エンドポイント

```
POST https://api.twitter.com/2/tweets
Authorization: OAuth 1.0a
Content-Type: application/json

{
  "text": "投稿テキスト"
}
```

---

## 文字数制限

| 制限 | 文字数 |
|---|---|
| X 公式制限 | 140文字（Unicode）|
| 推奨上限 | 120文字（リプライスペース確保） |

日本語はほぼすべて1文字カウント（一部絵文字は2カウント）。

---

## posted_results への書き込み（Phase 3-D で追加）

Phase 3-D では投稿成功後に `posted_results` タブへ記録する:

```python
sheets.save_result(
    queue_id=queue_id,
    draft_id=draft_id,
    account_id=account_id,
    platform="x",
    status="POSTED",
    posted_url=posted_url,
    external_post_id=post_id,
)
sheets.update_queue_item(queue_id, status="POSTED")
```

Phase 3-C では `posted_results` への書き込みは行わない。

---

## Rate Limit 注意

| API | Free Tier 制限 |
|---|---|
| POST /tweets | 月 500 件（Essential） |

月 500 件を超えると投稿できなくなる。  
初回テストは 1件のみで実施し、結果を確認してから量産する。
