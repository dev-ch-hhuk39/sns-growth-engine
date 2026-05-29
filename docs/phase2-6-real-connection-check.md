# Phase 2.6: 実接続テスト手順書

## 概要

`.env` に認証情報を設定した後、迷わずに以下を確認できる手順をまとめた。

1. Gemini 実 API が使える
2. Google Sheets 実接続ができる
3. 12 タブが存在する
4. シードが投入できる
5. Sheets から accounts / categories / prompts を読める
6. Gemini 実 API で draft 生成できる
7. Sheets には dry-run 中は書き込まない
8. --test-write 時だけテスト書き込みできる
9. run_pipeline が --use-sheets でも安全に動く
10. Phase 3 に進めるか自動診断できる

---

## 前提

- `v2/.env` が存在し、必要な項目が設定済みであること
- まだ SNS 本番投稿はしない（`PUBLISH_ENABLED=false` のまま）

---

## 推奨実行順序

### Step 1: .env 設定

```bash
cd v2
cp .env.template .env
# .env を開いて以下を設定:
#   SNS_MASTER_SHEET_ID=<スプレッドシートID>
#   SA_JSON_BASE64=<base64エンコードしたサービスアカウントJSON>
#   GEMINI_API_KEY=<GeminiAPIキー>
```

### Step 2: 設定確認

```bash
python scripts/print_env_status.py
```

**成功条件:** 必須項目がすべて `set` と表示される  
**失敗時:** `.env` を編集して未設定の項目を追加する

---

### Step 3: Gemini API 疎通確認

```bash
python scripts/test_gemini_real.py
```

**成功条件:** `PASS / 0 FAIL`  
**失敗時:** [troubleshooting.md](./troubleshooting.md) の「Gemini API エラー」を参照

---

### Step 4: Sheets API 疎通確認（読み取りのみ）

```bash
python scripts/test_sheets_connection.py --dry-run
```

**成功条件:** 各タブの読み取りが PASS  
**失敗時:** [troubleshooting.md](./troubleshooting.md) の「Sheets 接続エラー」を参照

---

### Step 5: Sheets セットアップ内容を確認（dry-run）

```bash
python scripts/setup_and_verify.py --dry-run
```

**成功条件:** 作成予定のタブ・シードが表示される（書き込みなし）

---

### Step 6: Sheets セットアップ実行

```bash
python scripts/setup_and_verify.py --setup --verify
```

**成功条件:** 12タブ作成 + accounts/categories/templates 確認OK  
**注意:** 冪等設計なので複数回実行しても安全

---

### Step 7: Sheets テスト書き込み

```bash
python scripts/setup_and_verify.py --test-write
```

**成功条件:** logs/drafts にテスト行が書き込まれる  
**注意:** SNS には投稿しない。テスト行は手動削除可

---

### Step 8: 総合診断

```bash
python scripts/preflight_check.py
```

**成功条件:** 総合判定 `READY_FOR_TEST_WRITE` または `READY_FOR_REAL_DRY_RUN`  
**失敗時:** FAIL/WARN の内容を確認して対処

---

### Step 9: パイプライン dry-run（Gemini実 + Sheets実読み取り）

```bash
python scripts/run_pipeline.py \
  --account-id night_scout \
  --platforms x,threads \
  --limit 2 \
  --dry-run --use-sheets
```

**成功条件:**  
- `MODE: REAL_LLM + REAL_SHEETS_READONLY` が表示される  
- `SHEETS_WRITE: false (dry-run)` が表示される  
- drafts / derivatives / queue が生成される（Sheets への書き込みなし）

---

### Step 10: パイプライン実書き込みテスト

```bash
python scripts/run_pipeline.py \
  --account-id night_scout \
  --platforms x,threads \
  --limit 1 \
  --use-sheets --test-write
```

**成功条件:**  
- `MODE: REAL_LLM + REAL_SHEETS_WRITE (test-only)` が表示される  
- Sheets の drafts / social_derivatives / queue タブに行が追加される  
- SNS には投稿しない

---

## 安全ガード確認

実行のどの段階でも以下が守られていること:

| チェック項目 | 確認方法 |
|---|---|
| PUBLISH_ENABLED=false | `python scripts/print_env_status.py` |
| SNS 投稿なし | 出力に `SNS_POSTING: disabled` が表示される |
| dry-run 中の書き込みなし | `SHEETS_WRITE: false (dry-run)` が表示される |

---

## 次のステップ

Phase 3 に進む条件は [phase3-go-no-go.md](./phase3-go-no-go.md) を参照。
