# check_pipeline_integrity.py 使い方

実際の Google Sheets データを読み取り、パイプラインデータの整合性を検証するスクリプト。
[PASS]/[WARN]/[FAIL] で問題を報告する。

---

## 基本的な使い方

```bash
cd v2

# 実Sheetsに対してチェック（推奨）
python scripts/check_pipeline_integrity.py --account-id night_scout

# WARN でも非ゼロ終了コードにする
python scripts/check_pipeline_integrity.py --account-id night_scout --fail-on-warn

# 全アカウント
python scripts/check_pipeline_integrity.py

# モック（実データ検証不可、構造確認のみ）
python scripts/check_pipeline_integrity.py --mock
```

---

## チェック項目

### drafts タブ

| チェック | 判定基準 |
|---|---|
| score カラム | 空行があれば [WARN]（--setup 実行で解消） |
| status 値 | DRAFT/READY/REVIEW/POSTED/REJECTED/ARCHIVED 以外は [FAIL] |

### social_derivatives タブ

| チェック | 判定基準 |
|---|---|
| draft_id 参照 | 対応する draft がなければ [WARN] |
| status 値 | 定義外の値は [FAIL] |
| text カラム | 空行があれば [WARN] |

### queue タブ

| チェック | 判定基準 |
|---|---|
| WAITING_REVIEW | 件数があれば [WARN]（review_queue.py で確認） |
| READY | 0件なら [WARN]（キューが空） |
| status 値 | 定義外の値は [FAIL] |

### logs タブ

| チェック | 判定基準 |
|---|---|
| level カラム | 空行があれば [WARN]（--setup 実行で解消） |
| ERROR レベル | 1件以上あれば [WARN]（内容確認推奨） |

### posted_results タブ

| チェック | 判定基準 |
|---|---|
| レコード数 | Phase 2 時点では0件が正常。あれば [WARN] |

---

## 出力例

```
============================================================
  check_pipeline_integrity.py - パイプライン整合性チェック
============================================================

対象: night_scout
────────────────────────────────────────────────────────────

[drafts]
  [PASS] drafts 取得OK: 3件
  [PASS] drafts.score は全行に値あり
  [PASS] drafts.status は全行正常

[social_derivatives]
  [PASS] social_derivatives 取得OK: 6件
  [PASS] social_derivatives の draft_id 参照整合性OK
  [PASS] social_derivatives.status は全行正常
  [PASS] social_derivatives.text は全行に値あり

[queue]
  [PASS] queue 取得OK: 4件
  [WARN] queue.status=WAITING_REVIEW が 4件あります
  [PASS] queue.status=READY: 0件 (Phase 3 投稿待ち)

[logs]
  [PASS] logs 取得OK: 8件
  [PASS] logs.level は全行に値あり
  [PASS] logs に ERROR レベルのログなし

[posted_results]
  [PASS] posted_results は空（Phase 2 正常状態）

============================================================
チェック結果サマリー:
  [PASS]: 11件
  [WARN]: 1件
  [FAIL]: 0件
============================================================

[RESULT] WARN: 問題の可能性がある項目があります。内容を確認してください。
```

---

## 終了コード

| コード | 意味 |
|---|---|
| 0 | 正常（FAIL なし） |
| 1 | [FAIL] あり、または `--fail-on-warn` 指定時に [WARN] あり |

---

## 運用タイミング

- `run_pipeline.py --test-write` 実行後
- Phase 3 移行前の最終確認
- 定期的なデータ品質確認
