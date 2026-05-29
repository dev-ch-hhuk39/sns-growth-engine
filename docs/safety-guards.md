# 安全ガード仕様

## 概要

本システムは SNS 本番投稿のリスクを排除するために複数の安全ガードを実装している。
Phase 3 実装前は絶対に本番SNS投稿を行わない。

---

## 環境変数による安全ガード

| 変数 | デフォルト | 効果 |
|---|---|---|
| `DRY_RUN=true` | false | シート書き込み & LLM 呼び出しを両方モック化 |
| `MOCK_LLM=true` | false | LLM 呼び出しのみモック（シート書き込みは行う） |
| `MOCK_SHEETS=true` | false | Sheets を MockSheetsClient に強制切替 |
| `PUBLISH_ENABLED=false` | false | Phase 3 以降まで false のまま（SNS 投稿処理ガード） |

---

## PUBLISH_ENABLED ガード

`queue_builder.py` に `_assert_publish_enabled()` 関数を定義している。

```python
_PUBLISH_ENABLED = os.environ.get("PUBLISH_ENABLED", "false").strip().lower() in ("1", "true", "yes")

def _assert_publish_enabled(operation: str) -> None:
    if not _PUBLISH_ENABLED:
        raise NotImplementedError(
            f"{operation}: PUBLISH_ENABLED=false のため投稿処理は実行できません。"
        )
```

Phase 3 で X API / Threads API を呼ぶ関数は、先頭で `_assert_publish_enabled("x_post")` を呼ぶこと。

---

## CLI フラグによる安全制御

| フラグ | 意味 |
|---|---|
| `--dry-run` | シートに書き込まない |
| `--mock-llm` | Gemini API を呼ばない |
| `--mock-sheets` | MockSheetsClient を強制使用 |
| `--use-sheets` | 実 SheetsClient を使用（認証情報必須） |
| `--test-write` | Sheets へのテスト書き込みを許可（--use-sheets が必要） |

### 排他チェック（run_pipeline.py / main.py）

- `--test-write` と `--dry-run` は同時指定不可
- `--test-write` には `--use-sheets` が必要
- `--mock-sheets` と `--use-sheets` は同時指定不可

---

## MockSheetsClient

認証情報なしで動くインメモリモッククライアント。

- 読み取り: `seeds.py` のデータを返す
- 書き込み: インメモリリストに蓄積（シートには書き込まない）
- `make_client(cfg, dry_run=True, force_mock=False)`:
  - `force_mock=True` → 常に MockSheetsClient
  - 認証情報なし + `dry_run=True` → MockSheetsClient（フォールバック）
  - 認証情報あり → SheetsClient

---

## DRY_RUN と MOCK_LLM の違い

| | DRY_RUN=true | MOCK_LLM=true |
|---|---|---|
| LLM 呼び出し | モック | モック |
| Sheets 書き込み | スキップ（コンソール出力のみ） | 実行 |
| 用途 | 完全なオフライン確認 | 実シートへの書き込み確認（API料金節約） |

---

## Phase 3 移行前のチェックリスト

- [ ] Phase 2 の dry-run が完全に通っている
- [ ] Gemini 実 API でのテストが通っている（`test_gemini_real.py`）
- [ ] Google Sheets 実接続で読み取り確認済み（`test_sheets_connection.py --dry-run`）
- [ ] X Developer Account 取得済み
- [ ] Threads API アクセス取得済み
- [ ] accounts.auto_publish を TRUE に変更（現在は FALSE）
- [ ] `.env` の `PUBLISH_ENABLED=true` に変更
