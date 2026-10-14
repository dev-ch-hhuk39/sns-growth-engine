# Phase 5B-6AI / 6AJ — Two offline snapshots, temporary shadow parity and safety evidence

Created 2026-10-14 JST. Additive, **unapplied Mac patch** based on local commit
`f4bf7e21e96f1d561e6414a03e044c488e5c1df6`. The combined bundle also
includes its previously unintegrated Phase 6AH files.

## Confirmed starting point

- Operational Threads queue and posted results still have legacy Google Sheets
  write paths; the protected SQLite CAS rehearsal and existing mirror/outbox
  tables have no actual posting authority. The local 6H AST inventory recorded
  165 direct Sheets write sites (71 P0) at the last connected development run.
  **Those figures are historical, not verified fresh production state.**
- Phase 6AH already validates a single metadata-only offline export but does
  not prove the data stayed unchanged during a migration staging window.
- Neither the source credentials nor complete provider export are cryptographically
  attested. Two matching files can both be incomplete or deliberately altered.

## Phase 6AI: compare two captured source views

New `scripts/p0_pair_shadow_parity.py` compares two copies of the schema
`sns_operational_queue_offline_metadata_v1`, with the same strict allowlist of
queue/post metadata fields from Phase 6AH. It refuses the following conditions:

- missing, colliding, added or removed queue IDs and posted-result identities;
- changed account, slot, route, status, media marker or posted-result metadata;
- unauthorized Beauty/media/X scope, missing verified result, unknown posting
  outcome, stale/future snapshot or unexpected content/secrets;
- different captures separated by more than 45 seconds, an identical capture
  timestamp, or any input older than 90 seconds at preflight;
- an empty queue, a missing declared legacy writer inventory or a changed
  source view after inspection.

Row ordering is ignored; complete metadata value differences are not. Safe
reports show only aggregate counts and fixed codes, not post IDs, queue IDs,
URLs, captions, tokens or source payloads. `pair_status=PASS_LOCAL_METADATA_ONLY`
means only that **two untrusted metadata views match locally**. It does not
mean provider provenance or production cutover is approved.

## Phase 6AJ: in-memory SQLite shadow import and verification

Test-only schema `scripts/fixtures/sql/p0_shadow_parity_memory_schema.sql` defines a
**test-only**, append/insert-only batch, queue and posted-result shadow. It must
not be installed on the operational database.

- `initialize_ephemeral_shadow()` accepts *only* an SQLite `:memory:` main
  database with foreign keys enforced, no attached database and an explicit
  test flag. On-disk, shared, read-only or operational connections are rejected.
- `stage_in_ephemeral_sqlite()` independently rechecks a fresh, unchanged
  preflight decision, starts one `BEGIN IMMEDIATE` transaction, stages only
  per-run HMAC identities, account scope and status, and commits atomically.
- Readback compares the inserted HMAC rows, counts and a canonical manifest to
  the **second** snapshot. Unknown storage outcome, injected write failure,
  missing row or changed metadata does not return a success result.
- SQLite triggers refuse UPDATE/DELETE on shadow tables. Nothing exposes a
  publisher or Sheets mutation interface. The only results are
  `STAGED_BLOCKED` or `VERIFIED_TEMPORARY_METADATA_ONLY` with
  `publish_authorized=false`, `production_cutover_authorized=false` and
  `operational_sqlite_write_authorized=false`.
- HMAC keys exist only in the process, and the whole SQLite database is discarded
  after the CLI returns. No genuine caption or media is copied.

## Read-only operator invocation after Mac integration

Requires *two distinct*, recently exported, operator-approved **minimal
metadata-only** JSON files in the already used 6AH schema, each with an
explicit observation timestamp. These timestamps are not proof of provider
freshness, so operational approvals remain blocked.

```sh
python3 scripts/rehearse_p0_pair_shadow.py \
  --before /private/exports/queue-before.json \
  --after /private/exports/queue-after.json \
  --simulate \
  --output /tmp/sns-p0-pair-shadow-new-report.json
```

Return code **2**, including when the temporary shadow copy verifies; the
output report must be a *new* absolute path outside the checkout, written as
mode 0600 and never overwritten. No `--apply` exists. Reports and input exports
must not be committed.

## Additional local integration safety checks

- The memory-only SQL schema is located under `scripts/fixtures/sql/`, **not**
  `db/migrations/`. This prevents an ordinary production migration collector
  from treating a synthetic shadow schema as a deployable operational table.
- A separate synthetic CLI run supplied two recently timestamped JSON files
  through the same metadata validation interface. It confirmed that a stable
  pair stages only in `:memory:` and returns exit 2, `CUTOVER_BLOCKED`,
  `VERIFIED_TEMPORARY_METADATA_ONLY`, and a redacted 0600 report. A modified
  second export returned a blocking metadata-drift finding and staged nothing.
- The guarded installer was exercised against **temporary mock Git repos**:
  initial combined installation, prior-6AH overlay installation, and injected
  full-gate failure. The latter restored the mock original HEAD and clean
  worktree without a commit. These are installer simulations; the real Mac
  checkout and original repo-wide quality gate were **not** executed.

## Test evidence and remaining actions

- Isolated packaging environment: **62/62 unit tests PASS** for the combined
  Phase 6AH + 6AI/AJ patch; Python `compileall` and shell syntax PASS.
  Coverage includes duplicate/cross-account results, Beauty/media scope,
  false data freshness, row reordering, changed metadata, appended/deleted
  results, disk DB rejection, foreign keys, temporary SQLite rollback,
  immutable tables, replay/stale preflight and explicit CLI refusal to apply.
- The exact Mac checkout could not be updated because Desktop Commander hit its
  monthly usage quota; the source artifact and local installer therefore remain
  **not integrated**, and Mac repo-wide QA / Git commit are unverified.
- `apply_to_local_mac.sh` checks the branch, clean worktree and `f4bf7e2`
  ancestry. It accepts either an untouched `f4bf7e2` checkout (combined
  installation) or a descendant with byte-for-byte identical Phase 6AH files
  and the expected registered test (overlay). It rolls back file changes if
  focused/full QA fails and never pushes or deploys. No force update is used.
- Production still needs named primary/backup writer ownership, provider
  identity + least-privilege ACL, operator-verified complete Sheets source
  exports, external process disablement, restore tests, a CAS-protected
  **actual publishing sink** and idempotency reconciliation, signed rights,
  authorized canaries, provider readback and 24h/72h/168h learning evidence.
  No offline metadata test can replace these actions.

**X publishing remains disabled. Beauty account real-media publishing requires
its existing independent rights/approval machinery; nothing here enables it.**
