# Phase 5B-6E — SQLite shadow queue and transactional source adapter

**Scope: development-only, non-authorizing. Main remains unchanged until PR CI.**

## Why a shadow queue, rather than directly switching Google Sheets

The prior review ledger (5B-5A), reconciliation (5B-5C), intent (5B-6B)
and dispatch stage (5B-6C) are all in one private SQLite database. The
operational queue/plan/receipt reader, however, still originates in a
separate store. A Sheets read is never a SQLite transaction and the source
may drift between approval and publication. This phase introduces the
missing **local transactional snapshot substrate** first. It does *not*
declare Google Sheets replaced or production publication safe.

## Added files

- `db/migrations/0006_sns_media_shadow_queue.sql`: explicit migration 0006
  after 0001–0005; private queue heads and append-only, hash-linked events.
- `scripts/media_shadow_queue_authority.py`: authenticated `capture`,
  `observe`, internal `SQLiteShadowOperationalSnapshot.load`, and
  hash-only `inspect`. No HTTP server, scheduler, Sheets client, SNS
  publisher, secrets or credentials are provisioned.
- `scripts/test_media_shadow_queue_authority.py`: offline RSA-signed
  reviewer + private SQLite + protected evidence + fixture-owned
  operational snapshot tests, including the existing review/intent/dispatch
  chain running against the SQLite-backed reader.
- The PR CI gate includes the focused tests so the module cannot silently
  drift while other code is modified.

## Guardrails

1. **Authentication and source.** `capture` and `observe` require
   `PinnedRS256SessionVerifier`, an unrevoked server-held MFA-backed
   reviewer session with account scope, and a server-provided
   `CanonicalProtectedReviewReader`. The original vault, sessions and
   ledger must use the **same** SQLite connection. Client JSON, raw Sheets
   fields, unsigned cookies and locally supplied reviewer names are never
   accepted as proof of authorization. The source reader must be created
   by a trusted backend, not a request handler or a JSON fallback.
2. **Snapshot validation.** The complete `plan`, review receipt history,
   queue identity/revision and original evidence are validated against the
   existing strict precommit contract. The source is fetched **once per
   operation**; a frozen in-memory context is reused for verification.
   Account/slot/queue, receipt draft, rights/territory/scope, reviewer,
   quality flags and proof freshness must all match. Credential-shaped
   keys/content and snapshots over 256 KiB are refused before storage.
3. **Single-store transaction.** `BEGIN IMMEDIATE` and expected
   head version/hash checks give atomic queue snapshot/event updates
   **inside SQLite only**. Event IDs are unique. A failed journal insert
   rolls back the head. Neither capture nor observe calls Sheets writes.
4. **Review freeze.** Snapshot `REFRESH` is only permitted before **any**
   review event, reconciliation binding, publish intent or dispatch exists.
   After any review (including revoked history), the same candidate cannot
   silently change its caption/media/revision. Changed source data must be
   handled as a conflict, not a new approval.
5. **Reconciliation.** `observe` fetches the independently owned
   operational snapshot again. Exact match adds a `SHADOW_BLOCKED`
   observation and renews a short read lease; mismatched source content
   permanently changes state to `CONFLICT_BLOCKED`. Missing source,
   revoked rights or failed source verification moves to
   `SOURCE_UNAVAILABLE_BLOCKED`. Both are terminal in this generation.
6. **Bounded internal reads.** The `SQLiteShadowOperationalSnapshot`
   adapter provides the saved `plan`, `receipts` and `queue` to the
   existing `CanonicalProtectedReviewReader`. Each read verifies head
   and event integrity, a 90-second last-observed lease, strict queue and
   receipt validity, fresh original evidence and unchanged evidence
   fingerprints. It fails closed if any check fails.
7. **No publication permit.** All returns contain
   `publish_authorized=false`, `effective_approval=false`,
   `dispatch_allowed=false`, and
   `external_queue_atomicity_guaranteed=false`. The 5B-6A direct
   Threads/X media network interlock is unchanged.

## Lifecycle

| Action | Before | After | External mutation |
|---|---|---|---|
| `capture` first trusted snapshot | No snapshot | `SHADOW_BLOCKED` v1 | None |
| `capture` CAS refresh | SHADOW, no review history | `SHADOW_BLOCKED` next version | None |
| `observe` exact unchanged source | SHADOW | `SHADOW_BLOCKED` next version; lease renewed | None |
| `observe` changed queue/plan/rights | SHADOW | `CONFLICT_BLOCKED` | None |
| `observe` missing source or invalid proof | SHADOW | `SOURCE_UNAVAILABLE_BLOCKED` | None |
| `SQLiteShadowOperationalSnapshot.load` | Fresh nonconflicted shadow | Read-only, same DB | None |

Terminal conflict states never turn into `READY`, never free duplicate
media reservations and never reopen merely because a retry is attempted.
A changed source should be handled as a new human-review process under a
new, explicit queue identity after future policy review.

### Transactional integration example (offline conceptual API)

The trusted server explicitly initializes migrations 0001–0006 on its
private DB, constructs `CanonicalProtectedReviewReader` with its own
server-owned source and vault, and calls `MediaShadowQueueAuthority.capture`
with its pinned session verifier. It then injects the following **internal**
reader (not the external Sheets reader) into the unchanged review, intent
and dispatch modules:

```python
internal_reader = CanonicalProtectedReviewReader(
    source=SQLiteShadowOperationalSnapshot(
        db=db, vault=ProtectedEvidenceVault(db)
    ),
    vault=ProtectedEvidenceVault(db),
)
# All downstream operations must share db and its BEGIN IMMEDIATE transaction.
# Successful review/intents/dispatch remain NON-authorizing.
```

No bootstrapping CLI, Google account access, live IdP, automatic periodic
poller, or production database migration is added by this phase.

## Explicit remaining risks

- **NOT a completed source-of-truth migration.** An external Google Sheets
  change inside the observation lease can still invalidate reality before
  the next `observe`. The 90-second lease bounds but cannot remove the
  cross-store race. Offline tests using a synthetic backend do not prove
  freshness or identity production readiness.
- **No worker switch to media publishing.** The real posting path still
  refuses protected media at both the publisher and direct helper layers,
  regardless of SQLite review/intent/dispatch states and flags.
- **Storage security.** The private shadow head stores actual plan, receipt
  and queue content to permit exact revalidation. Only a protected database
  volume, least-privilege credentials, encrypted backups and approved data
  retention controls should ever hold production data. Hash-chain events
  are not independently signed/externally anchored.
- **No automatic Sheets synchronization or cutover.** Eventual production
  work must make a server-side queue the operational write authority; use
  Sheets as an asynchronously replicated read-only view, control writer
  migration, prove no legacy bypass and protect an atomic one-time posting
  claim plus uncertain API outcomes.
- **No real IdP/service identity or egress restrictions.** Existing reviewer
  identity is not a publisher identity. Establish independent scoped
  publisher service authorization and network-level enforcement before
  enabling even a canary.

## Developer verification

```bash
python3 scripts/test_media_shadow_queue_authority.py
python3 scripts/test_media_dispatch_guard.py
python3 scripts/test_media_publish_intent_authority.py
python3 scripts/test_phase5b6d_network_sink_inventory.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m compileall -q src scripts
git diff --check
```

## Dedicated common VPS handoff — do not act from development chat

Repository `dev-ch-hhuk39/sns-growth-engine`.
No VPS deployment, SSH, database migration, Sheets production write, cron,
service restart, key provisioning, social posting, or secret access was
performed during this source-only phase. A separate operational approval,
backup/restore rehearsal, isolated credentials, migration verification and
shared deploy lock are required for any future rollout.
