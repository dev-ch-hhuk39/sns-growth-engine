# Threads Operation Runbook

## Current Mode

The system is now Threads-first.

- `night_scout`: Threads enabled, X posting disabled.
- `liver_manager`: Threads enabled, X posting disabled.
- `beauty_account`: draft-only, real posting disabled.

## Daily Safe Flow

1. Verify Sheets state:

```bash
python3 scripts/recover_production_sheets_threads_first.py --verify-only
```

2. Review `投稿キュー`.
3. Run queue worker dry-run:

```bash
python3 scripts/process_threads_queue.py --account-id <account_id> --dry-run
```

4. For real post, execute only one row at a time and never retry immediately after failure:

```bash
PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true \
python3 scripts/process_threads_queue.py --account-id <account_id> --confirm-real-post --max-posts 1
```

5. Import Threads metrics manually after enough time has passed:

```bash
python3 scripts/import_threads_metrics_manual.py --result-id <result_id> --views 0 --likes 0 --comments 0 --follows 0 --dry-run
```

6. Refill review queue only after checking pending rows:

```bash
python3 scripts/refill_threads_queue.py --account-id <account_id> --count 1 --dry-run
```

## Hard Stops

- Do not post `beauty_account`.
- Do not run X posting.
- Do not download/cut/upload media.
- Do not enable Cloudinary upload.
- Do not enable transcription API.
- Do not set learning rules active automatically.
- Do not repost rows with `POSTED`, `PROCESSING`, `FAILED`, `POSTED_SAVE_FAILED`, or `DUPLICATE_BLOCKED`.

## Current Live Post State

- `night_scout`: first Threads post already completed before this recovery.
- `liver_manager`: one Threads post was executed during the 2026-06-24 recovery and recorded in `投稿結果`.

## Worker References

- Queue worker: `docs/threads-queue-worker.md`
- Metrics import: `docs/metrics-import-runbook.md`
- Manual Sheets checks: `docs/sheets-manual-check-guide.md`
