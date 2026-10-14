# Phase 5B-6AH — P0 sanitized snapshot and temporary SQLite cutover preflight

Created 2026-10-14 JST. Additive source-only patch based on local `f4bf7e2`, **not yet applied on the Mac**.

## Confirmed existing components

The repository already has `audit_queue_authority_cutover.py` with minimal-metadata snapshot parsing and frozen legacy-writer baseline verification, `plan_legacy_writer_cutover.py`, and `p0_queue_cas_rehearsal.py` with a separate local SQLite one-use CAS journal. The 5B-6AF/AG journal is nonauthorizing and deliberately not connected to the live Threads post sink.

## What this phase adds

A reusable offline validation step that consumes the same strict metadata schema, groups counts for Night/Liver/Beauty, and refuses migration staging on any of these conditions:

- duplicate queue IDs across accounts, invalid global identity, wrong platform or out-of-scope account;
- READY with missing slot/media-scope declaration, protected media or uncertified rights;
- unverified POSTED results, orphan or cross-account results, reused queue results or external post IDs;
- PROCESSING / POSTED_SAVE_* / PUBLISH_OUTCOME_UNVERIFIED rows awaiting manual reconciliation;
- stale/future source snapshots, unknown statuses, unexpected column names or unsafe types;
- any Beauty records (the current P0 test journal's active account scope still covers Night/Liver only).

Only after this **metadata-only** preflight has no findings can the CLI stage its approved synthetic observation hashes in a *temporary* SQLite rehearsal DB. The CLI never updates the real Sheets queue or changes database authority. The report is always `CUTOVER_BLOCKED` with `production_cutover_authorized=false`, `publish_authorized=false`, `sheets_write_authorized=false` and `provider_calls=0`. Even a clean snapshot cannot prove caption parity, authenticated source lineage or current media rights.

The synthetic source digest is SHA-256 of metadata and snapshot time, not a signed/provider-authenticated approval. It is not an idempotency token for live remote posting.

## Validation and status

- Pure analysis + mocked CLI unit suite: **27/27 passed** in an isolated container, stdlib only. No real Mac full suite was executed in this phase because Desktop Commander reached its monthly usage limit.
- The optional installer requires exactly the known local branch/HEAD and clean worktree. It registers the new regression, runs the local focused/full QA and commits on the Mac only if all checks pass.
- Incomplete: physical producer lock, operator credentials/ACL, source-of-truth transfer, provider canary, verified backups and restores, and real operational observations. No push, deployment, Google Sheets mutation or Threads/X post occurred.
