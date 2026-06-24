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
3. Pick one `WAITING_REVIEW` row.
4. Run dry-run:

```bash
python3 scripts/publish_threads_post.py --account-id <account_id> --text "<text>" --dry-run
```

5. For real post, execute only one row at a time and never retry immediately after failure.

## Hard Stops

- Do not post `beauty_account`.
- Do not run X posting.
- Do not download/cut/upload media.
- Do not enable Cloudinary upload.
- Do not enable transcription API.
- Do not set learning rules active automatically.

## Current Live Post State

- `night_scout`: first Threads post already completed before this recovery.
- `liver_manager`: one Threads post was executed during the 2026-06-24 recovery and recorded in `投稿結果`.
