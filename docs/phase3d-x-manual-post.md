# Phase 3-D: X 本番投稿 1件手動テスト手順

Phase 3-D で初めて X に本番投稿する際の手順書。
**最初の投稿は必ず 1件のみ。成功を確認してから量産へ移行する。**

---

## 前提条件

以下がすべて揃っていること:

- [ ] `python scripts/test_phase3d.py` → 全 PASS
- [ ] X Developer Account（Essential 以上）取得済み
- [ ] OAuth 1.0a の4項目取得済み（API Key/Secret + Access Token/Secret）
- [ ] `queue` タブに status=READY の X 投稿アイテムが存在する
- [ ] `python scripts/phase3_safety_check.py` → FAIL なし

---

## 手順

### Step 1: 安全確認

```bash
python scripts/phase3_safety_check.py
```

全 PASS / WARN のみであることを確認。FAIL があれば解決してから進む。

---

### Step 2: 認証情報確認

```bash
python scripts/test_x_credentials.py
```

`READY_FOR_CREDENTIAL_TEST` が出ることを確認。

---

### Step 3: .env を一時的に変更

```
PUBLISH_ENABLED=true
ALLOW_REAL_X_POST=true
```

⚠️ テスト完了後は必ず `false` に戻すこと。

---

### Step 4: READY キューを確認

```bash
python scripts/review_queue.py --account-id night_scout --status READY --platform x
```

投稿したいアイテムの `queue_id` をメモする。

---

### Step 5: dry-run で最終確認

```bash
python scripts/publish_queue.py \
  --account-id night_scout \
  --platform x --status READY --limit 1 \
  --dry-run
```

`[DRY_RUN/OK]` が出ることを確認。

---

### Step 6: 1件だけ本番投稿

```bash
python scripts/publish_queue.py \
  --account-id night_scout \
  --platform x --status READY --limit 1 \
  --confirm-real-post \
  --queue-id <queue_id> \
  --max-real-posts 1
```

`[OK] X投稿成功 tweet_id=...` が出れば成功。

---

### Step 7: 結果確認

```bash
python scripts/review_queue.py --account-id night_scout --status POSTED
```

`status=POSTED` に変わっていること、`posted_results` に記録があることを確認。

X のタイムラインでも実際の投稿を目視確認する。

---

### Step 8: .env を元に戻す（必須）

```
PUBLISH_ENABLED=false
ALLOW_REAL_X_POST=false
```

---

## 失敗した場合

投稿失敗時は `queue.status` は `READY` のままで、`queue.error` にエラーメッセージが記録される。

```bash
python scripts/review_queue.py --account-id night_scout --status READY
```

でエラー内容を確認し、原因を解決してから再実行する。

---

## 注意事項

- X API Free Tier は月 500 件まで（POST /tweets）
- 初回テストは 1件のみ。成功確認後に量産する
- `--max-real-posts` はデフォルト 0（指定しないと投稿しない安全設計）
- `--queue-id` で特定アイテムを指定することを強く推奨
- 投稿後は必ず `.env` の `PUBLISH_ENABLED` と `ALLOW_REAL_X_POST` を `false` に戻す
