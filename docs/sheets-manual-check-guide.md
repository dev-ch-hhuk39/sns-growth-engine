# Sheets Manual Check Guide

Use this guide to verify the recovered Google Sheets state manually.

## Required Tabs

Check these tabs first:

| Tab | Expected Rows |
|---|---:|
| `アカウント管理` | 3 |
| `投稿カテゴリ` | 17 |
| `プロンプト管理` | 5 |
| `収集元アカウント` | 17 |
| `動画収集元` | 4 |
| `投稿下書き` | 6 |
| `SNS投稿文` | 6 |
| `投稿キュー` | 6 |
| `投稿結果` | 4 or more |
| `学習ルール` | 3 |
| `メディア資産` | 0 is OK |

## Account Checks

- `night_scout`
  - `platform=threads`
  - `x_enabled=false`
  - `threads_enabled=true`
  - `active=true`
  - `cta_type=LINE_AND_DM`
  - `default_queue_status=WAITING_REVIEW`

- `liver_manager`
  - `platform=threads`
  - `x_enabled=false`
  - `threads_enabled=true`
  - `active=true`
  - `cta_type=LINE_AND_DM`
  - `default_queue_status=WAITING_REVIEW`

- `beauty_account`
  - `threads_enabled=false`
  - `active=false`
  - `status=draft_only`
  - `cta_type=NONE`
  - no queue rows

## Safety Checks

- `投稿キュー`: no `platform=x` rows from recovery seed.
- `投稿キュー`: worker が投稿するのは **`status=READY` の行のみ**。`WAITING_REVIEW` / `DRAFT` / `PLANNED` は投稿対象外（recovery seed は既定で `WAITING_REVIEW`）。
- `投稿キュー`: `READY` は `approve_queue.py` の人間承認、または `auto_approve_queue.py` のAUTO_READY条件通過でのみ付く（logs に `queue_approved` 互換証跡が残る）。生成系CLIが直接 `READY` を書いていないこと。
- `投稿キュー`: `platform=x` / `beauty_account` の行が `READY` になっていないこと。
- `投稿キュー`: rows already `POSTED`, `PROCESSING`, `FAILED`, `POSTED_SAVE_FAILED`, or `DUPLICATE_BLOCKED` must not be reposted.
- `投稿結果`: real Threads rows should include `queue_id`, `derivative_id`, `platform=threads`, `external_post_id`, `status=POSTED`, `metrics_status=PENDING|MEASURED|MANUAL_PENDING`, `real_post`, `media_used=false`, and `posted_text`.
- `投稿結果`: no duplicate `posted_text` for the same `account_id/platform/status=POSTED`.
- `学習ルール`: all `active=false`, `auto_apply=false`.
- `収集元アカウント`: `auto_priority_change_allowed=false`.
- `収集元アカウント` and `動画収集元`: `allow_download=false`, `allow_cut=false`, `allow_upload=false`.
- `メディア資産`: no row should be ready for upload.

## posted_results 整合性修復 (2026-06-25)

posted_results 既存行の新規カラム（metrics_status / real_post / media_used）が空のまま残っていた場合、
以下のスクリプトで安全に補正できる。

```bash
# 確認のみ
python3 scripts/repair_posted_results_integrity.py --audit

# 補正内容を確認（書き込みなし）
python3 scripts/repair_posted_results_integrity.py --dry-run

# 実際に補正
python3 scripts/repair_posted_results_integrity.py --apply
```

補正ルール:
- POSTED 行: metrics_status="" → "PENDING", real_post="" → "true", media_used="" → "false"
- RECOVERED 行: metrics_status="" → "MANUAL_PENDING", real_post="" → "true", media_used="" → "false"
- 既に正しい値があれば変更しない（idempotent）

この repair は `.github/workflows/threads-queue-worker.yml` に組み込み済みで、毎回 verify 前に自動実行される。

## Verification Command

```bash
python3 scripts/recover_production_sheets_threads_first.py --verify-only
```

Expected: `failed=0`（check 総数は **51 件**＝2026-06-25 snapshot の 33 件 → item J の media/metrics チェック等で +8 → READY 承認モデルで +10。`passed` は seed 充足状況で変動するが、`failed=[]` であれば合格）

- 2026-06-25 初回達成（posted_results 整合性修復後）
- 2026-06-25 再確認（night_scout 孤児投稿復旧後 count_queue_night_scout=2, count_posted_results=4）

## GitHub Actions Sheets Secrets

The `Threads Queue Worker` workflow requires these repository secrets before live dry-run can reach Sheets:

- `SNS_MASTER_SHEET_ID` or `SPREADSHEET_ID`
- `SA_JSON_BASE64` or `GCP_SA_JSON_BASE64`

If either group is missing, the workflow stops at `Guard Sheets secrets` with `BLOCKED`; no post or Sheets write occurs.
