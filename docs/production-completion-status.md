# Production Completion Status

Date: 2026-06-24

## Status

The project is operational for Threads-first manual review operation, and the queue worker implementation is now present for one-row-at-a-time processing.

## Completed

- Existing unpushed main commit was pushed to GitHub before recovery.
- Google Sheets tabs were audited.
- Empty production tabs were seeded.
- Read-after-write verification passed.
- CTA rules were applied to code, Sheets seed, prompt templates, and docs.
- X posting was disabled for recovery mode.
- `night_scout` and `liver_manager` Threads queues were seeded.
- `beauty_account` remains blocked.
- Cloudinary upload was not executed.
- Media download/cut/upload was not executed.
- One `liver_manager` Threads real post was executed and recorded.
- `scripts/process_threads_queue.py` added for queue row processing.
- `scripts/import_threads_metrics_manual.py` added for manual insights import.
- `scripts/refill_threads_queue.py` added for review queue refill.
- `.github/workflows/threads-queue-worker.yml` added as manual-only worker.
- `content-daily-dry-run.yml` switched to Threads-first queue dry-run/refill dry-run/publisher dry-run.

## Verification

- Sheets verification: 21 / 21 PASS.
- Required local tests: 18 / 18 scripts PASS.
- Credential readiness: READY for required items.
- Cloudinary: credentials SET, upload disabled.
- Cloudflare transcription: optional credentials missing, transcription disabled.
- Stricter local Sheets verification and worker dry-run against live Sheets: blocked by local approval credits.
- GitHub Actions dry-run attempted twice and classified: repository Sheets secrets missing, so the workflow stopped before queue processing.
- True dry-run implementation verified locally: worker/refill dry-run do not call `setup_all()` or write to Sheets.

## Remaining Manual Checks

- Confirm Google Sheets rows in `投稿キュー`, `SNS投稿文`, `投稿下書き`, and `投稿結果`.
- Run `python3 scripts/recover_production_sheets_threads_first.py --verify-only` once approval/network credits are restored.
- Run `python3 scripts/process_threads_queue.py --account-id night_scout --dry-run` and `--account-id liver_manager --dry-run` once approval/network credits are restored.
- Register Actions Sheets secrets (`SNS_MASTER_SHEET_ID` / `SA_JSON_BASE64` or aliases), then rerun `Threads Queue Worker` in `dry_run` mode.
- Confirm the live `liver_manager` Threads post visually.
- Review Threads insights after enough time has passed.
- Keep X disabled until X API billing/operation is intentionally resumed.
