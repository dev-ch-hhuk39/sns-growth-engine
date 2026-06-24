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
| `投稿結果` | 3 or more |
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
- `投稿キュー`: only `WAITING_REVIEW` or `PLANNED` rows.
- `投稿キュー`: rows already `POSTED`, `PROCESSING`, `FAILED`, `POSTED_SAVE_FAILED`, or `DUPLICATE_BLOCKED` must not be reposted.
- `投稿結果`: real Threads rows should include `queue_id`, `derivative_id`, `platform=threads`, `external_post_id`, `status=POSTED`, `metrics_status=PENDING|MEASURED|MANUAL_PENDING`, `real_post`, `media_used=false`, and `posted_text`.
- `投稿結果`: no duplicate `posted_text` for the same `account_id/platform/status=POSTED`.
- `学習ルール`: all `active=false`, `auto_apply=false`.
- `収集元アカウント`: `auto_priority_change_allowed=false`.
- `収集元アカウント` and `動画収集元`: `allow_download=false`, `allow_cut=false`, `allow_upload=false`.
- `メディア資産`: no row should be ready for upload.

## Verification Command

```bash
python3 scripts/recover_production_sheets_threads_first.py --verify-only
```

Expected: `verification_passed=21 failed=0`.

For the queue worker release, the stricter verifier contains 30 checks. Last successful full Sheets verification before this release was 21 / 21. The stricter 30-check runtime verification is pending because the local approval system ran out of credits while calling Google Sheets.

## GitHub Actions Sheets Secrets

The `Threads Queue Worker` workflow requires these repository secrets before live dry-run can reach Sheets:

- `SNS_MASTER_SHEET_ID` or `SPREADSHEET_ID`
- `SA_JSON_BASE64` or `GCP_SA_JSON_BASE64`

If either group is missing, the workflow stops at `Guard Sheets secrets` with `BLOCKED`; no post or Sheets write occurs.
