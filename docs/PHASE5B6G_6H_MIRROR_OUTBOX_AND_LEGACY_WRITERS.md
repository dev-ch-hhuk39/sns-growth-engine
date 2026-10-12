# Phase 5B-6G + 6H — Local mirror outbox and legacy Sheets writer inventory

**Development-only implementation. Neither production Google Sheets nor SNS
posting is changed. No live mirror delivery or ACK is claimed.**

## Summary

Phase 6F introduced an authenticated, SQLite-local managed queue and
**sanitized read-only preview** of each managed event. It did not atomically
queue the preview for future delivery or enumerate all existing Sheets
mutators. This phase adds both safeguards without silently transferring
authority away from live Sheets or enabling real posting.

### 6G: SQLite-local outbox and non-authorizing claim

- Migration `db/migrations/0008_sns_media_mirror_outbox.sql` adds outbox
  heads and an append-only hash-chain event log.
- `scripts/media_managed_queue_writer.py` now automatically calls
  `enqueue_in_managed_write` inside **the same BEGIN IMMEDIATE SQLite
  transaction** that inserts its event and sanitized mirror preview.
  A failure to insert the outbox row aborts **all** those writes, so a
  successful 0008-enabled managed update cannot silently omit its outbox.
  A private DB still at migration 0007 remains backwards compatible.
  0008 is **not** applied to any live service.
- A queue event's SHA-256 identifies its outbox record. One operational
  candidate may have several immutable writer versions and matching outbox
  records. Only the currently pinned/latest version can be claimed for
  inspection: older versions become terminal `SUPERSEDED_BLOCKED`.
- `MirrorOutbox.claim_preview` requires a current pinned-RS256,
  MFA-backed, account-scoped reviewer session bound to the **same private
  SQLite DB**. It checks event-chain integrity, expected CAS version/hash
  and the exact current immutable writer projection. Claiming returns only
  the safe mirror metadata (`view_only=true`, identity, hashes, status),
  never caption, media URLs or original proof payload.
- `MirrorOutbox.stop` permits `CANCELLED_BLOCKED` and
  `UNCERTAIN_BLOCKED` states, also requiring a signed scoped operator.
  An ambiguous outcome never automatically retries a claim. No implicit
  lease stealing or replay exists; the claim time window is 45 seconds.
- **There is no Sheets transport** and no real receiver-authenticated
  readback/ACK. `acknowledge_external_delivery` fails closed. An
  offline CLAIM is neither proof of successful delivery nor a grant to
  initiate a Google Sheets write. A live transport must use a separate
  service identity rather than the reviewer login.

All return values have `sync_executed=false`,
`mirror_confirmed=false`, `publish_authorized=false`,
`dispatch_allowed=false`, `sheets_write_allowed=false` and
`ready_transitions_performed=false`. The real Threads/X media
interlock is unchanged.

### 6G local states

| Action | From | To | External effect |
|---|---|---|---|
| ENQUEUE | authenticated managed writer event | `QUEUED_BLOCKED` | None |
| CLAIM | exact latest queue event, signed reviewer | `CLAIMED_BLOCKED` | None |
| SUPERSEDE | queued old version | `SUPERSEDED_BLOCKED` | None |
| CANCEL | queued or claimed | `CANCELLED_BLOCKED` | None |
| UNCERTAIN | claimed | `UNCERTAIN_BLOCKED` | None |

There is intentionally **no** `SENT`, `PUBLISHED`, `ACKED` or
`READY` state in this local-only release.

### 6H: Freeze the inventory of legacy Sheets mutations

`scripts/test_phase5b6h_legacy_sheets_mutation_inventory.py` uses AST
analysis to enumerate existing direct queue update/append calls and common
worksheet write methods throughout non-test Python files in `src/` and
`scripts/`. The current snapshot is committed as
`docs/PHASE5B6H_SHEETS_MUTATION_BASELINE.json`.

At initial capture, **66 files / 163 AST call sites** are in the inventory.
The new CI check fails when calls are added, removed or their per-file method
counts change unless the inventory has been consciously reviewed and
updated. It also independently ensures important queue writers are present.

The baseline is **not** an allowlist granting any old route permission to
touch protected media and is **not** proof all legacy paths are safe.
Unchanged writers remain in the repository (including workflows with
direct worksheet access) and are still subject to existing 5B-6A media
publish safety stops. AST heuristics do not catch every dynamic import,
alias, SQL trigger or service outside this repo. A production cutover
requires explicit callsite-by-callsite verification, provider permissions
and runtime network boundaries. Never simply delete all legacy writers
before the Golden acceptance cases are satisfied.

## Test and review

```bash
python3 scripts/test_media_mirror_outbox.py
python3 scripts/test_phase5b6h_legacy_sheets_mutation_inventory.py
python3 scripts/test_media_managed_queue_writer.py
python3 scripts/test_phase5b6d_network_sink_inventory.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m compileall -q src scripts
git diff --check
```

Offline tests cover signed reviewer access, no duplicate claims,
version supersession, no unauthorized delivery ACK, permanent uncertainty,
immutability/tampering and **rollback of writer+preview when a 0008 outbox
insert fails**. All tests use synthetic temp SQLite, ephemeral keys and
fake snapshot providers, not real Google Sheets or SNS endpoints.

## Next phases: substantive operational cutover

1. Establish **separate mirror service identity** and destination
   allowlisting, where the service has write access only to a *distinct*
   reporting spreadsheet/workbook (never the operational queue).
2. Build a Google Sheets mirror *transport* with read-before-retry,
   destination-version conflict detection, strict projection schema and
   verified readback. If the response is unknown, quarantine rather than
   creating duplicate rows. Add synthetic transport tests, then isolated
   canary with explicit operational approval.
3. Choose and migrate the actual production queue's authoritative writer.
   Move all 6H inventory paths behind that backend or disable them by
   reviewed staging rules, while preserving independent text-only
   publishing and existing safety gates.
4. Add independent publisher service authorization, atomic one-use
   delivery claim, rights validation immediately before network send,
   timeout/unknown outcome reconciliation, egress policy, rollback test,
   production source monitoring and operator canary. Only after these
   can media posting be considered for live enablement.

## Dedicated VPS handoff

No shared VPS, database migration, service restart, credential, deployed
job, production Sheet, Cloudinary upload or real social publishing action
was performed. Production deploy/migrate and rollback belong exclusively
to the dedicated common VPS management chat.
