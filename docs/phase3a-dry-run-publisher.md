# Phase 3-A: Dry-run Publisher 設計と安全手順

---

## Phase 3-A の目的

Phase 3（本番 SNS 投稿）に進む前に、**投稿処理の直前まで安全に流せる構造**を作る。

実 SNS API（X / Threads）は一切呼ばない。
`PUBLISH_ENABLED=false` を維持する。
`posted_results` には書かない。
`queue.status` は変更しない。

---

## Phase 3-A で実装したもの

### 1. publishers パッケージ

```
src/publishers/
  __init__.py     # パブリックAPI
  base.py         # BasePublisher + PublishResult
  dry_run.py      # DryRunPublisher
  factory.py      # get_publisher() ファクトリ
```

詳細: [publisher-interface.md](./publisher-interface.md)

### 2. publish_queue.py

queue の投稿候補を DryRunPublisher で検証する CLI。

```bash
# 基本的な使い方（--dry-run 必須）
python scripts/publish_queue.py \
  --account-id night_scout \
  --platforms x,threads \
  --status WAITING_REVIEW \
  --dry-run

# 1件のみ確認
python scripts/publish_queue.py \
  --account-id night_scout \
  --platform x \
  --limit 1 \
  --dry-run
```

安全保証:
- `--dry-run` なしで実行すると即終了（エラー）
- `PUBLISH_ENABLED=true` が検出されたら即終了
- `posted_results` への書き込みなし
- `queue.status` 変更なし
- `logs` に dry-run チェックログのみ記録

### 3. review_queue.py 強化

publish readiness（DryRunPublisher チェック結果）、risk summary、publish_queue.py コマンドの表示を追加。

### 4. phase3_safety_check.py 強化

`publishers/dry_run.py` の存在確認を追加。

---

## Phase 3-A の安全確認手順

```bash
cd v2

# Step 1: テスト
python scripts/test_phase2.py       # 31 PASS / 0 FAIL
python scripts/test_phase3a.py      # 全 PASS

# Step 2: キュー確認
python scripts/review_queue.py \
  --account-id night_scout \
  --status WAITING_REVIEW

# Step 3: dry-run 投稿チェック
python scripts/publish_queue.py \
  --account-id night_scout \
  --platforms x,threads \
  --status WAITING_REVIEW \
  --dry-run

# Step 4: 整合性・安全チェック
python scripts/check_pipeline_integrity.py --account-id night_scout
python scripts/phase3_safety_check.py
python scripts/preflight_check.py
```

---

## Phase 3-A で確認する項目

| 確認項目 | 期待値 | 確認方法 |
|---|---|---|
| 実 SNS 投稿 | なし | publish_queue.py の出力 |
| posted_results 増加 | なし | check_pipeline_integrity.py |
| queue.status 変更 | なし | review_queue.py で目視 |
| logs 変化 | dry-run ログのみ | check_pipeline_integrity.py |
| PUBLISH_ENABLED | false | phase3_safety_check.py |

---

## まだやらないこと（Phase 3-B 以降）

- X API / Threads API への実投稿
- `x_publisher.py` / `threads_publisher.py` の実装
- `PUBLISH_ENABLED=true` への変更
- `posted_results` への投稿結果書き込み
- `queue.status = POSTED` への更新

---

## Phase 3-B の準備条件

Phase 3-B（本番投稿）に進む前に以下をすべて満たす必要がある:

1. Phase 3-A の全テスト通過
2. `publish_queue.py --dry-run` で全アイテムが `[DRY/OK]` になること
3. X API アカウント取得（Essential 以上）
4. Threads API アクセストークン取得
5. `phase3_safety_check.py` 全 PASS
6. `preflight_check.py` → `READY_FOR_TEST_WRITE` 以上

詳細: [phase3-go-no-go.md](./phase3-go-no-go.md)
