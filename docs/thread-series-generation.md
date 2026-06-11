# Thread Series 生成ガイド（Phase 6.2）

## 概要

thread_series は root_hook から始まる reply ツリー形式の連続投稿。
アカウント設定駆動で生成し、全投稿は `WAITING_REVIEW` 状態で出力する。

---

## 1. 基本コマンド

### サンプル生成（dry-run / mock LLM）

```bash
# night_scout / X プラットフォーム
python scripts/generate_thread_series.py \
  --account-id night_scout \
  --platform x \
  --theme "夜職で月50万稼ぐ方法"

# beauty_account / Threads（draft_only アカウント）
python scripts/generate_thread_series.py \
  --account-id beauty_account \
  --platform threads \
  --post-count 5
```

### レビュー

```bash
python scripts/review_thread_series.py --account-id beauty_account
python scripts/review_thread_series.py --series-json path/to/series.json
```

### 承認（人間レビュー後）

```bash
python scripts/approve_thread_series.py \
  --series-json path/to/series.json \
  --confirm-approve
```

---

## 2. 投稿 role の説明

| role | 説明 |
|------|------|
| hook | 読者の興味を引く最初の1投稿 |
| context | なぜこれが重要なのか背景説明 |
| reason | 具体的な根拠・理由 |
| example | 具体例・事例 |
| checklist | チェックリスト形式の要点 |
| objection_handling | よくある反論への回答 |
| proof | 証拠・実績 |
| cta | 行動促進メッセージ |

---

## 3. draft_only アカウントの扱い

`beauty_account` などの `draft_only` アカウントは:

- 生成は可能（mock / LLM どちらも）
- 全投稿は `WAITING_REVIEW` 状態のまま
- `READY` 化・実投稿は禁止
- `generation_notes` に draft_only の注記が追加される

---

## 4. Sheets test-write

```bash
python scripts/generate_thread_series.py \
  --account-id night_scout \
  --test-write \
  --mock-llm
```

`--use-sheets` を追加すると実 Sheets に書き込む（要 service account 認証）。

---

## 5. 文字数制限

| プラットフォーム | soft 上限 | hard 上限 |
|-----------------|-----------|-----------|
| x | 120文字 | 140文字 |
| threads | 500文字 | 800文字 |

各アカウントの `platform_policy` で上書き可能。

---

## 更新履歴

- Phase 6.2: 初期作成（2026-06-11）
