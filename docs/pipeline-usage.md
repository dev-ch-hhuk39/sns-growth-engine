# パイプライン使用方法

## Phase 2.6 追加コマンド（実接続確認）

```bash
# 環境変数の設定状況確認（値は表示しない）
python scripts/print_env_status.py

# Phase 3 移行前 総合診断
python scripts/preflight_check.py
python scripts/preflight_check.py --quick    # API呼び出しなし

# Sheets セットアップ + 検証
python scripts/setup_and_verify.py --dry-run        # 実行内容を確認
python scripts/setup_and_verify.py --setup --verify # タブ作成 + シード投入 + 確認
python scripts/setup_and_verify.py --test-write     # テスト書き込み確認
python scripts/setup_and_verify.py --all            # 上記すべて実行
```

---

## 必要な .env 設定

```env
# 必須
SNS_MASTER_SHEET_ID=<スプレッドシートID>
SA_JSON_BASE64=<base64エンコードしたサービスアカウントJSON>
# または
GCP_SA_JSON=<サービスアカウントJSONをそのまま>

# Gemini
GEMINI_API_KEY=<GeminiAPIキー>
GEMINI_MODEL_CANDIDATES=gemini-2.5-flash-lite@v1beta,gemini-2.5-flash@v1beta,gemini-2.5-pro@v1beta

# 安全ガード（デフォルト値）
DRY_RUN=false
MOCK_LLM=false
MOCK_SHEETS=false
PUBLISH_ENABLED=false  # Phase 3 以降まで false のまま
```

---

## 動作モード一覧

| モード | コマンド | Gemini | Sheets | 書き込み |
|---|---|---|---|---|
| **Mode A** full mock | `--dry-run --mock-llm` | モック | Mock | なし |
| **Mode B** Gemini実 | `--dry-run` | 実 API | Mock(※) | なし |
| **Mode C** Sheets読 | `--dry-run --use-sheets` | 実 API | 実 Sheets | なし |
| **Mode D** test write | `--use-sheets --test-write` | 実 API | 実 Sheets | テスト書き込み |

(※) 認証情報未設定の場合は MockSheetsClient にフォールバック

---

## dry-run 手順（認証情報なしで確認）

```bash
cd v2

# パイプライン全体を dry-run + mock-llm で確認（Mode A）
python scripts/run_pipeline.py --account-id night_scout --platforms x,threads --limit 2 --dry-run --mock-llm

# 各ステップを個別に確認
python scripts/generate_drafts.py --account-id night_scout --limit 3 --dry-run --mock-llm
python scripts/generate_social_derivatives.py --account-id night_scout --platforms x,threads --limit 5 --dry-run --mock-llm
python scripts/build_queue.py --account-id night_scout --platforms x,threads --dry-run
```

---

## Gemini 実 API 確認

```bash
# Gemini 実 API 接続テスト（API キーが必要）
python scripts/test_gemini_real.py

# Mode B: Gemini実 + 書き込みなし
python scripts/run_pipeline.py --account-id night_scout --dry-run
```

---

## Google Sheets 実接続確認

```bash
# 読み取り確認のみ（書き込みなし）
python scripts/test_sheets_connection.py --dry-run

# Mode C: Gemini実 + Sheets実読み取り（書き込みなし）
python scripts/run_pipeline.py --account-id night_scout --dry-run --use-sheets
```

---

## テスト書き込み（Mode D）

```bash
# Sheets テスト行の書き込み確認
python scripts/test_sheets_connection.py --test-write

# Mode D: Gemini実 + Sheets実書き込み（SNS投稿なし）
python scripts/run_pipeline.py --account-id night_scout --use-sheets --test-write --limit 1
```

---

## mock-llm 手順

Gemini API キーなしで実際のシートに書き込みながら確認する場合:

```bash
# .env に SNS_MASTER_SHEET_ID と認証情報だけ設定して実行
python scripts/run_pipeline.py --account-id night_scout --limit 2 --mock-llm --use-sheets --test-write
```

---

## テスト実行

```bash
cd v2
# Phase 2 ユニットテスト（全モック）
python scripts/test_phase2.py

# Gemini 実 API テスト
python scripts/test_gemini_real.py

# Sheets 実接続テスト（読み取りのみ）
python scripts/test_sheets_connection.py --dry-run
```

---

## main.py 経由で実行

```bash
cd v2/src

# full mock（Mode A）
python main.py --run-pipeline --account-id night_scout --platforms x,threads --limit 2 --dry-run --mock-llm

# Gemini実 + Sheets実読み取り（Mode C）
python main.py --run-pipeline --account-id night_scout --dry-run --use-sheets

# Gemini実 + Sheets実書き込み（Mode D）
python main.py --run-pipeline --account-id night_scout --use-sheets --test-write --limit 1

# 個別ステップ
python main.py --generate-drafts --account-id night_scout --limit 5 --dry-run --mock-llm
python main.py --generate-derivatives --account-id night_scout --platforms x,threads --dry-run --mock-llm
python main.py --build-queue --account-id night_scout --platforms x,threads --dry-run
python main.py --setup-only --dry-run
```

---

## 本番運用時の実行手順（Phase 3 以降）

1. `.env` に全認証情報・`GEMINI_API_KEY` を設定
2. `python scripts/test_sheets_connection.py --dry-run` で Sheets 接続確認
3. `python scripts/test_gemini_real.py` で Gemini API 確認
4. `python scripts/run_pipeline.py --account-id night_scout --dry-run --use-sheets` で dry-run 確認
5. スプレッドシートの `queue` タブを確認
6. `status=WAITING_REVIEW` の投稿を手動確認して承認
7. `PUBLISH_ENABLED=true` に変更（Phase 3 実装後のみ）

---

## 注意事項

- 本番SNS投稿はまだ行いません（Phase 3 で実装）
- `PUBLISH_ENABLED=false`（デフォルト）の間は投稿処理が実行されません
- `DRY_RUN=true` のときは絶対にシートに書き込まれません
- `MOCK_LLM=true` のときは Gemini を呼び出しません（API 料金不要）
- `auto_publish=FALSE` のアカウントは queue が必ず `WAITING_REVIEW` になります
- `--test-write` と `--dry-run` は同時に指定できません
