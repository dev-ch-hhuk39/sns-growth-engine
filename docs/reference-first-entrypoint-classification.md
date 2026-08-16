# Reference-first Entry Point Classification

Updated: 2026-08-11

The machine-readable authority is
`config/reference_first_completion.json`. Every current workflow file and each
major runtime entry point is assigned exactly one class. The completion
evaluator fails on duplicate classifications, unknown workflow files, missing
files, or browser runtime references in active workflows.

## Classes

- `canonical`: the supported Reference-first preparation, review, CI, library
  health, source research, metrics or PDCA path.
- `inactive_compatibility`: retained to read historical state or support an
  explicitly invoked compatibility dry-run; not selected by active routing.
- `obsolete_dead`: historical evidence/repair tooling; not an execution path.
- `external_blocked`: executable code whose mutation requires explicit
  production approval, credentials, live permission evidence, or all of them.

Current inventory: 42/42 workflows and 28/28 major entry points classified.
No active workflow installs Playwright or consumes browser storage state.
Legacy browser adapters remain readable but are not selectable by
`config/source_backend_routing.json`.

## Active Path

1. `acquire_approved_source_posts.py` performs bounded normalized discovery.
2. Direct media and clip preparation use the shared latest-row permission
   ledger, exact source identity, exact parent attachment and content
   understanding.
3. Generation creates account-specific public text and stops at
   `WAITING_REVIEW`.
4. Human review is the only normal transition to `READY`.
5. `process_threads_queue.py` publishes only `READY`, revalidates public text
   and media, applies idempotency, verifies persisted results, and creates the
   24h/72h/7d metric jobs.
6. PDCA consumes only `MEASURED` observations and writes suggestions as
   `WAITING_REVIEW` with `auto_apply=false`.

## Bounded External Verification

The no-write command is:

```bash
python3 scripts/acquire_approved_source_posts.py \
  --account-id all --platform PLATFORM --max-posts 1 \
  --reference-only --verify-network
```

On 2026-08-11, YouTube returned one normalized post/media bundle through
`yt_dlp`. Threads public HTTP, TikTok `yt_dlp -> gallery-dl`, and X bounded
`gallery-dl` could not produce a public result in the current environment.
Those three are `UNVERIFIED_EXTERNAL`, not fake PASS and not an internal
software failure. The command never connects to Sheets and never downloads,
uploads, cuts or publishes media.

## Retirement Rule

Do not delete compatibility or obsolete files in this local checkpoint.
Retirement needs a separate reachability review after dual-account physical
Goldens exist for both X and YouTube. Historical evidence is not an active
fallback.
