# Sheets Recovery Report

Date: 2026-06-24
Mode: Threads-first production recovery

## Summary

Google Sheets was audited because most production tabs were empty. All target tabs existed and had headers, but only `アカウント管理` and `投稿結果` had data rows before recovery.

Recovery was performed with `scripts/recover_production_sheets_threads_first.py`.

## Before

Empty tabs before seed:

- `収集元アカウント`
- `動画収集元`
- `参考投稿`
- `収集済み投稿`
- `投稿カテゴリ`
- `投稿配分計画`
- `生成ジョブ`
- `投稿下書き`
- `SNS投稿文`
- `スレッド構成`
- `投稿キュー`
- `メディア資産`
- `動画文字起こし`
- `動画クリップ候補`
- `PDCA実行履歴`
- `改善提案`
- `学習ルール`
- `プロンプト管理`
- `実行ログ`

Non-empty before seed:

- `アカウント管理`: 3 rows
- `投稿結果`: 1 row

## Recovery Seed

- Accounts: 3 rows verified.
- Categories: 17 rows.
- Prompt templates: 5 rows.
- Source accounts: 17 rows.
- Video sources: 4 rows.
- Drafts: 6 rows.
- Social derivatives: 6 rows.
- Queue: `night_scout` 3 rows, `liver_manager` 3 rows, `beauty_account` 0 rows.
- Learning rules: 3 rows, all `active=false` and `auto_apply=false`.
- Media assets: 0 rows; no unapproved upload rows.
- Posted results: 3 rows after recovery and live post record.

## Read After Write

`python3 scripts/recover_production_sheets_threads_first.py --verify-only`

Result:

- verification: 21 / 21 PASS
- `night_scout` CTA: `LINE_AND_DM`
- `liver_manager` CTA: `LINE_AND_DM`
- `beauty_account` CTA: `NONE`
- `beauty_account active=false`
- no X queue
- no Cloudinary upload
- no media download/cut/upload

## Live Operation

- `night_scout`: dry-run PASS. No new real post because first Threads post already existed.
- `liver_manager`: dry-run PASS. One real Threads post executed once and recorded in `投稿結果`.
- `beauty_account`: blocked / draft-only.

## Warnings

- Google Sheets API returned read quota 429 during early runs. The script was optimized with worksheet caching and batch upserts, then read-after-write verification passed.
- X remains disabled for posting.
- Cloudinary credentials are set, but `ALLOW_CLOUDINARY_UPLOAD=false`; no upload was executed.
