# review_queue.py 使い方

投稿キューを確認するための **読み取り専用** ビューア。
queue タブのアイテムを drafts / social_derivatives と JOIN して表示し、
X投稿の文字数やThreads形式もチェックする。

---

## 基本的な使い方

```bash
cd v2

# WAITING_REVIEW のキューを確認（デフォルト）
python scripts/review_queue.py --account-id night_scout

# ステータス指定
python scripts/review_queue.py --account-id night_scout --status WAITING_REVIEW

# プラットフォーム絞り込み
python scripts/review_queue.py --account-id night_scout --platform x
python scripts/review_queue.py --account-id night_scout --platform threads

# 全ステータス表示
python scripts/review_queue.py --account-id night_scout --status all

# モック（実データなし、動作確認のみ）
python scripts/review_queue.py --mock
```

---

## 表示内容（Phase 3-A 強化版）

各キューアイテムについて以下を表示する:

```
───────────────────────────────────────────────
  queue_id    : q-xxxxxxxx
  draft_id    : d-xxxxxxxx
  platform    : X
  status      : WAITING_REVIEW
  scheduled_at: 2026-05-22T10:00:00Z

  [draft]
    title        : 夜の仕事を探している人へ...
    score        : 85  (pv=80 cv=75 brand_risk=10 [LOW_RISK])
    ai_review    : フック強度高。CTA自然。...
    cta_text     : 無料相談はこちら

  [social_derivative]
    文字数       : 98字
    text preview : 「もう普通の仕事には戻れない」...
    [OK]   X投稿文字数: 98字 (≤120字)

  [publish readiness]
    [DRY/OK]  DRY_RUN: would post to X (98字) | account=night_scout ...
    → publish_queue: python scripts/publish_queue.py --account-id night_scout ...
```

### Phase 3-A で追加された表示

| 項目 | 説明 |
|---|---|
| `[LOW_RISK]` / `[MED_RISK]` / `[HIGH_RISK]` | brand_risk_score による risk summary |
| `[publish readiness]` | DryRunPublisher による事前検証結果 |
| `[DRY/OK]` / `[DRY/WARN]` / `[DRY/FAIL]` | dry-run publish チェック結果 |
| `publish_queue:` | publish_queue.py で実行できるコマンドを表示 |

---

## フォーマットチェック

### X 投稿

| 文字数 | 判定 |
|---|---|
| 120字以下 | [OK] |
| 121〜140字 | [WARN] 推奨上限超過 |
| 141字以上 | [FAIL] X制限超過 |

X API の実際の制限は140字だが、URLの展開などを考慮して120字を推奨上限とする。

### Threads 投稿

フック（1行目）と本文の間に空行があるかチェックする。

| チェック内容 | 判定 |
|---|---|
| 空行あり（フック+本文形式） | [OK] |
| 空行なし | [WARN] |
| 2行以下 | [WARN] |

---

## 終了コード

| コード | 意味 |
|---|---|
| 0 | 正常（[FAIL] なし） |
| 1 | X投稿が140字超のアイテムあり |

---

## 注意事項

- このスクリプトはデータを変更しない（読み取り専用）
- 実Google Sheetsへの接続には `.env` の認証情報が必要
- WAITING_REVIEW のアイテムが0件の場合は正常終了
