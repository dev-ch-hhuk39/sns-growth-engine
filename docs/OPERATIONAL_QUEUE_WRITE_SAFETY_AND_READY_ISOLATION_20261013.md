# Operational queue write safety and scheduled READY isolation (local development)

Date: 2026-10-13 JST. Source-only work on the isolated Mac worktree after \`e46e0d1\`.
Nothing here is a production queue cutover or permission to publish.

## Why this batch was necessary

The operational Sheets queue and the protected SQLite media writer are **not one
atomic authority**. Some legacy Sheets mutation paths retried \`append_row\` or
\`batch_update\` after an unknown provider response. A remote request might have
already committed; replay could duplicate a persisted result or overwrite
a concurrent operator change. The old AUTO_READY path also wrote an \`OK\`
approval log **before** the queue mutation returned.

Meanwhile the older scheduled text path read a reusable file named by account
and slot in \`/tmp\`. An old successful JSON file could be mistaken for this
invocation's result if a new command had an inconsistent output.

Finally, \`reconcile_due_production_slots.reconcile\` returned overall PASS after
\`PRE_PUBLISH_FAILED\` and \`DELIVERY_FAILED_CONFIRMED\`. Claim release meant
no duplicate risk, **not** delivery success.

## Implemented changes

- \`src/sheets_client.py\`: use \`sheets_write_once\` for the legacy queue's
  single-row and bulk mutating updates; never automatically replay on timeout.
  Emit a sanitized \`SheetsMutationOutcomeUnknown\`, not provider error bodies,
  when a write or subsequent readback is uncertain. Keep read-only retry logic.
- Queue cell writes use \`RAW\` rather than \`USER_ENTERED\` to preserve literal
  IDs and strings (including strings beginning with \`=\`). Existing non-queue
  \`_batch_update_fields\` behavior is unchanged.
- Single queue mutations verify the exact persisted \`queue_id\` and updated
  fields through fresh row readback; a missing field or mismatched value blocks
  success.
- Bulk AUTO_READY mutations reject blank/repeated requested IDs, duplicated
  target IDs in the current grid and a stale \`READY\` transition source other
  than \`WAITING_REVIEW\`. After one bounded set of Sheets batch writes,
  re-read the full queue to verify all persisted field changes and uniqueness.
  Multiple 400-cell chunks remain **non-atomic**; a later uncertain chunk
  requires manual reconciliation, never automatic replay.
- \`scripts/process_threads_queue.py\`: existing publisher-side queue updates
  and posted-result appends now use one mutation attempt, never the legacy
  generic retry helper. A \`dry_run\` client is forbidden from these mutation
  calls. The existing publisher identity/readback and no-repost gates remain.
- \`scripts/auto_approve_queue.py\`: emit \`queue_approved: OK\` only after
  the operational queue writer has completed its checks. A failed or uncertain
  write does not record a false approval success.
- \`scripts/run_scheduled_text_slot_pipeline.py\`: every hybrid READY
  invocation uses a new \`tempfile.TemporaryDirectory\`, automatically cleaned
  after use, and requires a persisted JSON record with the **exact** account,
  slot, and selected queue ID. Missing, corrupt, or foreign identities fail
  closed and use the existing bounded text fallback path.
- \`scripts/reconcile_due_production_slots.py\`: aggregate operational status
  is FAILED for an intended slot with \`PRE_PUBLISH_FAILED\` or
  \`DELIVERY_FAILED_CONFIRMED\`, even if an unpublished claim can safely be
  released. This affects failure signals, not the replay boundary.

## Local verification and evidence

- New independent offline adversarial suites:
  \`test_legacy_queue_write_safety.py\` (9 cases),
  \`test_scheduled_ready_tempfile_isolation.py\` (5 cases).
- Existing media interlock fake Sheets now persists synthetic cell changes,
  so the production implementation's readback requirements can be tested
  without weakening rights/approval assertions.
- \`run_local_quality_gate.py --mode focused\` includes these new tests,
  \`test_buffered_reconciler.py\`, and the existing 6A interlock tests.
- The \`test_phase5b6h_legacy_sheets_mutation_inventory.py\` baseline must
  continue to PASS: this batch adds no unreviewed direct Sheets callsite.
- Final full Mac offline QA: **982/982 repository scripts PASS**; static
  workflow safety, Ruff fatal rules, Python compile, Git diff and local
  gitleaks history scan all PASS. The first run found one outdated MagicMock
  fixture with an implicit truthy `dry_run`; the fixture now explicitly
  represents a write-capable client, while dry-run writes remain blocked.
  The complete rerun PASS is the final result, not the initial failed run.
  The test fixtures and provider data are synthetic, not live evidence.

## Important scope limitations and next cutover stage

**No authoritative queue cutover has taken place.** Text READY and posting
are still backed by the operational Sheets queue. The protected SQLite writer
remains BLOCKED/view-only for media; neither one is a replacement for the other.

This implementation cannot provide Google Sheets compare-and-swap or
distributed exactly-once guarantees. Multiple legacy writers outside the
specific queue mutation paths remain in the historical 6H inventory and
still require explicit callsite-by-callsite migration/disablement and
reconciliation. Provider errors after a possible mutation must trigger
a read-only inspection of exact IDs and operator decision rather than a
blind rerun. No rollback of externally acknowledged updates is attempted.

The next heavy stage requires operations-approved authoritative source
selection, backup/restore, a verified real Google identity with restricted
permission, protected SQLite migrations, independent operator signoffs and
a one-source-at-a-time migration. The separate VPS management chat owns
host operations and real provider canaries.

No GitHub Actions, Codex, public push, runtime credential, paid API,
production Sheets write, SNS post, Cloudinary upload, or shared VPS operation
was performed by this local development batch.
