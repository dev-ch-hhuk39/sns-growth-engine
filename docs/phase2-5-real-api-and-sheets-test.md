# Phase 2.5: 実 API・実 Sheets 安全検証

## 目的

Phase 2 で確立した mock パイプラインを、実際の Gemini API と Google Sheets に接続して
安全に検証する。本番 SNS 投稿は行わない。

---

## 4 つの動作モード

| モード | コマンド例 | Gemini | Sheets | 書き込み |
|---|---|---|---|---|
| **Mode A** | `--dry-run --mock-llm` | モック | Mock | なし |
| **Mode B** | `--dry-run` | 実 API | Mock/フォールバック | なし |
| **Mode C** | `--dry-run --use-sheets` | 実 API | 実 Sheets | なし |
| **Mode D** | `--use-sheets --test-write` | 実 API | 実 Sheets | テスト書き込みのみ |

---

## 検証手順

### Step 1: Mode A（full mock）

認証情報なしで動作を確認する。

```bash
cd v2
python scripts/run_pipeline.py \
  --account-id night_scout \
  --platforms x,threads \
  --limit 2 \
  --dry-run --mock-llm
```

期待結果:
- `[INFO] MOCK-LLM` と `[INFO] DRY-RUN` が表示される
- MockSheetsClient を使用
- 書き込みなし

---

### Step 2: Gemini 実 API 接続確認

```bash
python scripts/test_gemini_real.py
```

期待結果:
- `GEMINI_API_KEY` が未設定なら `[SKIP]` で終了（exit 0）
- 設定済みなら `3 PASS / 0 FAIL`

---

### Step 3: Google Sheets 実接続確認（読み取りのみ）

```bash
python scripts/test_sheets_connection.py --dry-run
```

期待結果:
- 認証情報未設定なら `[SKIP]` で終了（exit 0）
- 設定済みなら各タブの読み取り結果を表示
- 書き込みは行わない

---

### Step 4: Mode C（Gemini実 + Sheets実読み取り）

```bash
python scripts/run_pipeline.py \
  --account-id night_scout \
  --platforms x,threads \
  --limit 2 \
  --dry-run --use-sheets
```

期待結果:
- Gemini で実際のテキストを生成
- 実 Sheets から accounts / categories を読み取り
- Sheets には書き込まない

---

### Step 5: Mode D（実書き込み確認）

スプレッドシートにテスト行を書き込む。実行前に確認すること。

```bash
python scripts/test_sheets_connection.py --test-write
```

または

```bash
python scripts/run_pipeline.py \
  --account-id night_scout \
  --platforms x,threads \
  --limit 1 \
  --use-sheets --test-write
```

期待結果:
- Sheets の drafts / social_derivatives / queue タブにテスト行が追加される
- SNS には投稿しない

---

## 既存プロジェクトへの影響ゼロ確認

Phase 2.5 の変更対象は `v2/` 以下のみ。
以下の既存プロジェクトには一切変更しない:

- `夜職_x/`
- `夜職_threads/`
- `ライバー/`

確認コマンド:

```bash
# 既存プロジェクトのファイルが変更されていないことを確認
ls 夜職_x/ 夜職_threads/ ライバー/
```

---

## 安全ガード

- `PUBLISH_ENABLED=false`（デフォルト）の間は SNS 投稿処理は実行されない
- `_assert_publish_enabled()` が NotImplementedError を投げてガードする
- `--test-write` は Sheets への書き込みのみ（SNS 投稿なし）
