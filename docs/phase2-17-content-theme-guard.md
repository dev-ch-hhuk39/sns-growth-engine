# Phase 2.17 — コンテンツテーマガード

**実装日**: 2026-05-31  
**ステータス**: 完了

---

## 背景

night_scout の READY キューに、ターゲット（キャバ嬢・夜職女性）ではなく代理店・パートナー候補に向けた投稿が混入していた。  
根本原因: `ns_08`（代理店向け投稿）カテゴリが `active=TRUE` のまま機能し、プロンプトにも禁止事項が明示されていなかった。

---

## 実装内容

### 1. Sheetsデータ修正

| 対象 | 変更前 | 変更後 |
|------|--------|--------|
| queue: q-7cdc6567 (X) | READY | REJECTED |
| queue: q-fcc966be (Threads) | WAITING_REVIEW | REJECTED |
| draft: d-efc7f39b | DRAFT | REJECTED |
| draft: d-ff32252b | WAITING_REVIEW | REJECTED |
| category: ns_08 | active=TRUE | active=FALSE |
| category: lm_08 | active=TRUE | active=FALSE |

### 2. seeds.py

- `ns_08`, `lm_08`: `active=FALSE` に変更（将来のキャンペーン用に保持、削除しない）
- `_DRAFT_GEN_NIGHT_SCOUT` の `## 絶対NG` に代理店系禁止事項を追加
- `ACCOUNT_FORBIDDEN_KEYWORDS` を追加（Sheetsには格納しない）
- `ACCOUNT_FORBIDDEN_THEMES` を追加

### 3. reference_based_generator.py

- `_get_account_ng_block(account_id)` 追加
- `build_reference_based_prompt()` / `build_original_hypothesis_prompt()` でアカウント固有NGブロックをプロンプトに注入

### 4. approval_scorer.py

| 関数 | 役割 |
|------|------|
| `detect_forbidden_keywords(text, keywords)` | 本文内の禁止キーワード検出 |
| `calculate_target_fit_score(draft, account_config)` | 0.0〜1.0のターゲット適合スコア |
| `check_content_theme(draft, account_config)` | テーマチェック結果dict |
| `apply_content_theme_guard(score_result, draft, account_config)` | スコア結果にガード適用 |

`score_generated_post()` に `account_config` 引数を追加し、テーマガードを統合。

### 5. generate_from_jobs.py

生成後に `detect_forbidden_keywords` でチェック。  
ヒット → `status=WAITING_REVIEW`（REJECTEDにはしない: 機械検出は人間確認でデグレードさせる）

### 6. approve_queue.py

`cmd_approve()` 内、READY変更前に social_derivative のテキストをチェック。  
ヒット → READY変更を拒否。`--reject` で明示的に却下させる。

### 7. check_pipeline_integrity.py

- `VALID_QUEUE_STATUSES` に `"REJECTED"` を追加
- `check_content_theme_in_queue()` 追加: READY キューの禁止キーワードを `[WARN]` で通知

---

## 禁止キーワード一覧

### night_scout

```python
["代理店", "パートナー募集", "代理店パートナー", "紹介業",
 "スカウト代理店", "組織的に稼ぐ", "組織的なロジック", "高収益",
 "稼ぎ方を教えます", "ノウハウを共有", "ビジネス構造", "収益モデル"]
```

### liver_manager

```python
["代理店", "パートナー募集", "情報商材"]
```

---

## 設計判断

- **REJECTED vs WAITING_REVIEW**: 機械検出で自動REJECTED は誤検出リスクがある。`generate_from_jobs.py` では WAITING_REVIEW に留め、人間が最終判断する。
- **approve_queue.py は READY拒否**: キュー昇格時のゲートは厳格に。ここは人間が操作するポイントなので強く止める。
- **forbidden_keywords は seeds.py**: Sheetsはリスト型データを格納しにくいため、Pythonコードで管理する。
- **[WARN]のみ**: check_pipeline_integrity.py では歴史データを考慮し FAIL ではなく WARN とする。
