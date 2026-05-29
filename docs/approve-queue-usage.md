# approve_queue.py 使い方

queue の WAITING_REVIEW 投稿を人間が READY / REJECTED に変更するための CLI。

---

## 基本的な使い方

```bash
cd v2

# 1. まず review_queue.py で確認
python scripts/review_queue.py --account-id night_scout --status WAITING_REVIEW

# 2. 一覧のみ表示（approve_queue.py --list）
python scripts/approve_queue.py --account-id night_scout --status WAITING_REVIEW --list

# 3. 1件承認（WAITING_REVIEW → READY）
python scripts/approve_queue.py --queue-id q-xxxx --approve --reason "内容確認済み、投稿可"

# 4. 1件却下（WAITING_REVIEW → REJECTED）
python scripts/approve_queue.py --queue-id q-xxxx --reject --reason "表現が強すぎる"

# 5. ステータスを直接指定
python scripts/approve_queue.py --queue-id q-xxxx --status READY --reason "手動承認"

# 6. dry-run（Sheets を変更せず確認のみ）
python scripts/approve_queue.py --queue-id q-xxxx --approve --reason "テスト" --dry-run
```

---

## 承認フロー

```
review_queue.py で確認
  ↓
approve_queue.py --approve / --reject
  ↓
queue.status が READY / REJECTED に変更
  ↓
logs に承認/却下ログが記録される
  ↓
publish_queue.py --status READY --dry-run で再確認
```

---

## オプション一覧

| オプション | 説明 |
|---|---|
| `--queue-id` | 対象 queue_id（変更時必須） |
| `--approve` | status を READY に変更 |
| `--reject` | status を REJECTED に変更 |
| `--status READY/REJECTED` | status を直接指定 |
| `--reason` | 承認/却下の理由（変更時必須） |
| `--list` | 一覧表示のみ（読み取り専用） |
| `--dry-run` | Sheets を変更せず確認のみ |
| `--account-id` | --list 時のフィルタ |
| `--platform` | --list 時のフィルタ |

---

## 表示される内容

```
────────────────────────────────────────────────────────
  queue_id    : q-xxxxxxxx
  draft_id    : d-xxxxxxxx
  platform    : X
  status      : WAITING_REVIEW
  scheduled_at: 2026-05-22T20:00:00+0900

  [draft]
    title      : スカウト代理店の稼ぎ方...
    score      : 85  (pv=70 cv=90 brand_risk=10 [LOW_RISK])
    ai_review  : 現状でも十分ターゲットに...

  [投稿テキスト]
    文字数   : 94字
    内容     : 「スカウトは稼げない」はもう古い...

  [publish readiness]
    [DRY/OK]  DRY_RUN: would post to X (94字) | account=night_scout ...
    判定     : READY推奨

  変更内容: WAITING_REVIEW → READY
  reason  : 内容確認済み

[OK] queue_id=q-xxxxxxxx の status を READY に変更しました
     ※ SNS 本番投稿は行っていません
     ※ posted_results への書き込みは行っていません
```

---

## ログに残る内容

承認時:
```
operation: queue_approved
level    : INFO
message  : queue_approved: queue_id=q-xxx WAITING_REVIEW→READY
details  : queue_id=q-xxx platform=x WAITING_REVIEW→READY reason='内容確認済み'
```

却下時:
```
operation: queue_rejected
level    : INFO
message  : queue_rejected: queue_id=q-xxx WAITING_REVIEW→REJECTED
details  : queue_id=q-xxx platform=x WAITING_REVIEW→REJECTED reason='表現が強い'
```

---

## READY 後の次ステップ

```bash
# READY になったキューを publish_queue.py で dry-run 確認
python scripts/publish_queue.py \
  --account-id night_scout \
  --platforms x,threads \
  --status READY \
  --dry-run
```

Phase 3-C（本番投稿）は X API / Threads API 実装後に実行予定。

---

## 注意事項

- `--reason` なしでは変更できない（必須）
- `--dry-run` では Sheets を変更しないが、ログには dry-run 記録が残る
- REJECTED になったアイテムは `publish_queue.py` の対象外
- このスクリプトで SNS 投稿は発生しない
- `posted_results` への書き込みは行わない
