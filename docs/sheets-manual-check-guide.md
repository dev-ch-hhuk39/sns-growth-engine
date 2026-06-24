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
- `学習ルール`: all `active=false`, `auto_apply=false`.
- `収集元アカウント`: `auto_priority_change_allowed=false`.
- `収集元アカウント` and `動画収集元`: `allow_download=false`, `allow_cut=false`, `allow_upload=false`.
- `メディア資産`: no row should be ready for upload.

## Verification Command

```bash
python3 scripts/recover_production_sheets_threads_first.py --verify-only
```

Expected: `verification_passed=21 failed=0`.
