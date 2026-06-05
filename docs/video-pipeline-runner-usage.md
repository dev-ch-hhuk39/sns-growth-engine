# 動画パイプライン統合実行 使用ガイド

**作成日**: 2026-06-06

---

## 概要

`run_video_pipeline.py` は動画パイプラインの全ステップをシーケンシャルに実行する統合 CLI。

---

## 全体フロー（統合実行）

```
Step 1: ソース確認 (reference_sources)
  ↓
Step 2: 動画収集状態確認 (reference_posts)
  ↓
Step 3: 文字起こし (transcribe)
  ↓
Step 4: クリップ候補抽出 (analyze)
  ↓
Step 5: クリップ切り抜き dry-run (cut)
  ↓
Step 6: 投稿文生成 (generate)
  ↓
Step 7: パイプライン整合性チェック (integrity)
```

---

## コマンド一覧

### 全ステップ実行（モック・推奨）

```bash
python scripts/run_video_pipeline.py --account-id night_scout
```

### 実Sheets + mockLLM + 書き込みあり（推奨テスト手順）

```bash
python scripts/run_video_pipeline.py \
  --account-id night_scout \
  --use-sheets --test-write --mock-llm
```

### 実Sheets + 実LLM + 書き込みあり

```bash
python scripts/run_video_pipeline.py \
  --account-id night_scout \
  --use-sheets --test-write --no-mock-llm
```

### 特定ステップのみ実行

```bash
# 文字起こしと候補抽出のみ
python scripts/run_video_pipeline.py \
  --account-id night_scout \
  --steps transcribe,analyze

# 生成のみ
python scripts/run_video_pipeline.py \
  --account-id night_scout \
  --steps generate
```

---

## 引数一覧

| 引数 | デフォルト | 説明 |
|---|---|---|
| `--account-id` | 必須 | アカウントID |
| `--use-sheets` | false | 実Google Sheets 接続 |
| `--test-write` | false | Sheets 書き込み有効化 |
| `--mock` | false | MockSheetsClient 強制 |
| `--mock-llm` | true | LLM モック使用 |
| `--no-mock-llm` | - | 実LLM 使用 |
| `--confirm-api` | false | 文字起こし実API許可 |
| `--steps` | all | 実行ステップ（カンマ区切り） |
| `--limit` | 10 | 文字起こし対象動画の上限 |
| `--n-candidates` | 6 | 動画1本あたりのクリップ候補数 |

---

## 安全ガード

| ガード | 設定 |
|---|---|
| デフォルト dry-run | `--test-write` なし |
| MockSheetsClient | `--use-sheets` なし |
| 文字起こし実API禁止 | `ALLOW_TRANSCRIPTION_API=false` + `--confirm-api` なし |
| 切り抜き実行禁止 | Step 5 は常に dry-run |
| SNS 本番投稿禁止 | コード実装保証 |
