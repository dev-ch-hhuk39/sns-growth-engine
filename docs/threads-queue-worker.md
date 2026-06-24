# Threads Queue Worker

Date: 2026-06-24

## Purpose

`scripts/process_threads_queue.py` processes Google Sheets `投稿キュー` rows for Threads-first operation.

It is intentionally narrow:

- account: `night_scout` or `liver_manager`
- platform: `threads`
- eligible status: `WAITING_REVIEW` or `PLANNED`
- default batch: 1 row
- hard cap: 2 rows
- `beauty_account`: blocked
- X rows: ignored

## Safety Gates

Real posting requires all of the following:

```bash
PUBLISH_ENABLED=true
ALLOW_REAL_THREADS_POST=true
python3 scripts/process_threads_queue.py --account-id night_scout --confirm-real-post --max-posts 1
```

The worker always performs a Threads publisher dry-run before real posting.

Duplicate guards block:

- same `queue_id` already in `posted_results`
- same `derivative_id`
- same `draft_id` already `POSTED` or `RECOVERED`
- same `posted_text` for the same account/platform already `POSTED`

## Commands

```bash
python3 scripts/process_threads_queue.py --account-id night_scout --dry-run
python3 scripts/process_threads_queue.py --account-id liver_manager --dry-run
```

Real mode:

```bash
PUBLISH_ENABLED=true ALLOW_REAL_THREADS_POST=true \
python3 scripts/process_threads_queue.py --account-id night_scout --confirm-real-post --max-posts 1
```

## Failure Handling

- post failure: queue row becomes `FAILED`; no immediate retry
- duplicate: queue row becomes `DUPLICATE_BLOCKED` in real mode
- posted_results save failure after a successful post: queue row becomes `POSTED_SAVE_FAILED`, fallback JSON is written to `output/posted_results_fallback/`, and the row must not be reposted

## GitHub Actions

`.github/workflows/threads-queue-worker.yml` is manual-only (`workflow_dispatch`).

It runs:

1. Sheets verify
2. queue worker dry-run
3. process queue only if `mode=real_post` and `confirm_real_post=true`
4. Sheets verify after processing

No schedule is configured.
