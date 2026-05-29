# Phase 3-B: 承認フロー設計と安全手順

---

## Phase 3-B の目的

X API / Threads API に接続する前に、**人間が投稿候補を確認・承認する仕組み**を作る。
本番投稿 API は一切接続しない。`PUBLISH_ENABLED=false` を維持する。

---

## Phase 3-B で実装したもの

### 1. SheetsClient への queue メソッド追加

```python
# 読み取り
sheets.get_queue_items(account_id, platform, status, limit)
sheets.get_queue_item(queue_id)

# 書き込み（status 変更のみ）
sheets.update_queue_item(queue_id, status="READY", ...)
```

### 2. approve_queue.py

queue の WAITING_REVIEW → READY / REJECTED を変更する CLI。

詳細: [approve-queue-usage.md](./approve-queue-usage.md)

### 3. review_queue.py 強化（承認補助）

各キューアイテムに以下を追加表示:
- `[READY推奨]` / `[要確認]` / `[REJECT推奨]` 判定
- `approve_queue.py` の実行コマンド例

### 4. publish_queue.py の対象 status 明確化

| status | 対象 |
|---|---|
| `WAITING_REVIEW` | ✓ dry-run 検証対象 |
| `READY` | ✓ dry-run 検証対象 |
| `REJECTED` | ✗ 対象外（エラー終了） |
| `POSTED` | ✗ 対象外（エラー終了） |
| `FAILED` | ✗ 対象外（エラー終了） |

---

## 承認フロー全体

```
1. run_pipeline.py --test-write
     ↓ queue に WAITING_REVIEW で積まれる

2. review_queue.py --status WAITING_REVIEW
     ↓ 投稿テキスト・スコア・リスク・DRY/OK を確認

3. approve_queue.py --queue-id q-xxx --approve --reason "理由"
     ↓ queue.status = WAITING_REVIEW → READY
     ↓ logs に queue_approved ログを記録

   または

   approve_queue.py --queue-id q-xxx --reject --reason "理由"
     ↓ queue.status = WAITING_REVIEW → REJECTED
     ↓ logs に queue_rejected ログを記録

4. review_queue.py --status READY
     ↓ 承認済みキューを確認

5. publish_queue.py --status READY --dry-run
     ↓ DryRunPublisher で投稿直前の最終確認

6. （Phase 3-C 以降）本番 Publisher で実際に投稿
```

---

## Phase 3-B の安全確認手順

```bash
cd v2

# Step 1: テスト
python scripts/test_phase3b.py

# Step 2: 一覧確認
python scripts/approve_queue.py \
  --account-id night_scout --status WAITING_REVIEW --list

# Step 3: 1件承認（実 Sheets）
python scripts/approve_queue.py \
  --queue-id <queue_id> --approve --reason "内容確認済み"

# Step 4: READY になったことを確認
python scripts/review_queue.py --account-id night_scout --status READY

# Step 5: READY の dry-run 確認
python scripts/publish_queue.py \
  --account-id night_scout --status READY --dry-run

# Step 6: 安全チェック
python scripts/phase3_safety_check.py
```

---

## Phase 3-B の安全保証

| 確認項目 | 保証 |
|---|---|
| SNS 本番投稿 | なし（API 未接続） |
| posted_results 書き込み | なし |
| PUBLISH_ENABLED | false 維持 |
| queue.status 変更 | approve_queue.py --approve/--reject 明示時のみ |
| logs | 承認/却下ログのみ追記 |

---

## まだやらないこと（Phase 3-C）

- X API への実投稿（`x_publisher.py` 未実装）
- Threads API への実投稿（`threads_publisher.py` 未実装）
- `PUBLISH_ENABLED=true` への変更
- `posted_results` への投稿結果書き込み
- `queue.status = POSTED` への更新

---

## Phase 3-C の準備条件

1. Phase 3-B の全テスト通過
2. `publish_queue.py --status READY --dry-run` で全アイテムが `[DRY/OK]`
3. `approve_queue.py` で READY になったアイテムが存在する
4. X API Developer Account 取得済み
5. Threads API アクセストークン取得済み
6. `x_publisher.py` / `threads_publisher.py` 実装
7. `phase3_safety_check.py` 全 PASS

詳細: [phase3-go-no-go.md](./phase3-go-no-go.md)
