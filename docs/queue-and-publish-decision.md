# queue と publish_decision の仕様

## draft.status の意味

| status | 意味 |
|---|---|
| `DRAFT` | スコアが min_publish_score 未満。要改善。 |
| `READY` | 全条件パス。派生投稿生成・queue 追加の対象。 |
| `HUMAN_REVIEW` | brand_risk_score が閾値超過。人間確認待ち。 |
| `REJECT` | AI が明示的にNGと判定（外部から設定した場合）。 |

## social_derivatives.status の意味

| status | 意味 |
|---|---|
| `READY` | queue に積める状態。auto_publish の判定で変わる。 |
| `HUMAN_REVIEW` | draft の brand_risk_score が高い。人間確認待ち。 |
| `REJECT` | Gemini が REJECT と判定。queue に積まない。 |

## queue.status の意味

| status | 意味 |
|---|---|
| `READY` | 自動投稿可。auto_publish=TRUE かつ全条件パス。Phase 3 で投稿処理を実装。 |
| `WAITING_REVIEW` | 手動確認待ち。auto_publish=FALSE または条件未達。 |
| `REJECTED` | queue に積まない。 |
| `POSTED` | 投稿済み（Phase 3 以降に設定）。 |
| `FAILED` | 投稿失敗（Phase 3 以降に設定）。 |

---

## publish_decision の判定ロジック

### decide_draft_status(draft, account)

```
1. brand_risk_score > brand_risk_threshold → HUMAN_REVIEW
2. combined_score < min_publish_score       → DRAFT
3. それ以外                                  → READY

combined_score = (score + cv_score) / 2  ※ cv_score > 0 の場合
```

### decide_derivative_status(derivative, draft, account)

```
1. Gemini が REJECT と判定 → REJECT
2. draft.brand_risk_score > threshold → HUMAN_REVIEW
3. それ以外 → READY
```

### should_queue(derivative, draft, account) → (add, queue_status, reason)

```
1. derivative.status == REJECT → (False, REJECTED, ...)
2. derivative.status == HUMAN_REVIEW → (True, WAITING_REVIEW, ...)
3. account.auto_publish != TRUE → (True, WAITING_REVIEW, ...)
4. brand_risk_score > threshold → (True, WAITING_REVIEW, ...)
5. combined_score < min_publish_score → (True, WAITING_REVIEW, ...)
6. すべてパス → (True, READY, ...)
```

---

## accounts テーブルの設定値

| カラム | 意味 | デフォルト |
|---|---|---|
| `auto_publish` | TRUE なら queue.status=READY、FALSE なら WAITING_REVIEW | FALSE |
| `min_publish_score` | この値以上の score が必要 | 65 |
| `brand_risk_threshold` | この値を超えると HUMAN_REVIEW | 25 |
| `post_time` | 投稿時刻（HH:MM）。scheduled_at の計算に使用 | 20:00 |
| `timezone` | タイムゾーン（IANA形式） | Asia/Tokyo |

---

## scheduled_at の計算方法

1. accounts.timezone で現在時刻を取得
2. accounts.post_time（HH:MM）で当日の目標時刻を作成
3. 当日の目標時刻を過ぎていれば翌日に設定
4. ISO 8601 形式（+0900 等）で queue.scheduled_at に保存

Phase 3 で実際の投稿処理が scheduled_at を読んで実行します。
