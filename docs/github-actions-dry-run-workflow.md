# GitHub Actions Dry-Run Workflow

## 概要

`.github/workflows/v2-dry-run-check.yml`

本番投稿なしの安全確認専用 GitHub Actions workflow。
`workflow_dispatch` のみで実行可能（schedule は使用しない）。

## 安全制約

workflow 内で以下のフラグを **env:** で固定:

```yaml
PUBLISH_ENABLED: "false"
ALLOW_REAL_X_POST: "false"
ALLOW_REAL_THREADS_POST: "false"
ALLOW_TRANSCRIPTION_API: "false"
ALLOW_CLOUDINARY_UPLOAD: "false"
DRY_RUN: "true"
MOCK_LLM: "true"
MOCK_SHEETS: "true"
```

これらのフラグは workflow ファイル内で変更禁止。

## 実行方法

1. GitHub リポジトリの Actions タブへ移動
2. "v2 Dry-Run Safety Check" workflow を選択
3. "Run workflow" ボタンをクリック
4. account_id を入力（デフォルト: night_scout）
5. 実行

**今回（Phase 5実装時）はworkflowを実行しない。**
次回ユーザーが準備できた時点で実行する。

## 実行ステップ

| ステップ | 内容 |
|---------|------|
| Verify safety flags | 安全フラグが全て false であることを確認 |
| Phase 2 tests | 基本機能テスト |
| Phase 3 safety check | 安全ガード確認 |
| Preflight check (quick) | 環境変数・インポート確認（API なし） |
| Preflight video / X | プレフライト（--mock）|
| Pipeline integrity | パイプライン整合性確認（--mock）|
| Learning integrity | 学習整合性確認（--mock）|
| Phase 5 smoke plan | dry-run のみ |
| Phase 5 tests | 新規テスト実行 |
| Verify no real posts | 実投稿が発生していないことを確認 |

## secrets 設定なしでも動作する設計

- `MOCK_SHEETS=true` のため Sheets API 不要
- `MOCK_LLM=true` のため Gemini API 不要
- secrets が設定されていなくてもテストの多くは `continue-on-error: true` で続行

secrets がある場合は以下を設定:
- `SNS_MASTER_SHEET_ID`
- `SA_JSON_BASE64`
- `GEMINI_API_KEY`

## 禁止パターン

以下は workflow に追加しない:

```yaml
# 禁止
env:
  PUBLISH_ENABLED: "true"        # 禁止
  ALLOW_REAL_X_POST: "true"      # 禁止
  ALLOW_TRANSCRIPTION_API: "true" # 禁止
  ALLOW_CLOUDINARY_UPLOAD: "true" # 禁止
```

## セキュリティ注意事項

- `run:` 内でユーザー入力を直接展開しない（injection リスク）
- `env:` を介して環境変数として渡す
- secrets 値を echo しない
- ログに認証情報を出力しない

例（実装済み）:
```yaml
- name: Phase 5 smoke plan dry-run
  env:
    ACCOUNT_ID: ${{ github.event.inputs.account_id }}
  run: python scripts/run_real_smoke_plan.py --step all --account-id "$ACCOUNT_ID"
```

## 関連ファイル

- `.github/workflows/v2-dry-run-check.yml` - workflow 本体
- `scripts/test_github_actions_dry_run_workflow.py` - workflow テスト
