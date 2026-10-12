# Phase 5B-6I — Isolated mirror service identity and offline readback trial

**Development-only. The transport is an exact in-memory fake, not an enabled
Google Sheets integration, real acknowledgement, or production cutover.**

## Motivation

Prior Phase 5B-6G introduced an outbox that records safe projection events,
but only human reviewers can inspect those claims. A reviewer JWT must
never be reused as a Google Sheets service principal. Production Sheets
is still the operational system of record, separate from SQLite.
No media publishing may be enabled on the basis of a shadow, outbox claim,
simulation, or successful GitHub CI.

## Added

- `db/migrations/0009_sns_media_mirror_rehearsal.sql`: independent service
  sessions, destination-scoped reporting-only grants, and append-only
  hash-chained rehearsal receipt heads/events. Provisioned by a
  trusted operator only; none are provisioned in production by this phase.
- `scripts/media_mirror_rehearsal.py`: `PinnedMirrorServiceVerifier`
  accepts only a **server-pinned RS256** signature, exact issuer,
  audience `sns-growth-mirror-rehearsal`, explicit
  `mirror_rehearsal_only` token use, exact `mirror:rehearse`
  scope and up-to-5-minute service tokens. It verifies the hash of
  the full JWT and signed JTI against a currently enabled, unrevoked,
  server-provisioned SQLite service session.
- A separate destination registry binds an account ID, service subject,
  distinct operational and reporting spreadsheet IDs, and a tab named
  `mirror_preview_*`. It requires
  `ISOLATED_REPORTING_ONLY` and enabled=1. This is a **local policy**;
  actual Google Sheets ACLs and ownership are not provisioned or verified.
- `MirrorServiceRehearsal` accepts **only** its concrete
  `InMemoryReportingReplica` (no arbitrary transport object,
  plugin, HTTP client, Google API or service credentials) and the same
  SQLite connection as its pinned service verifier.
- The worker requires a 6G `CLAIMED_BLOCKED` event issued through an
  authenticated reviewer, within its 45-second lease, and
  rechecks the exact currently pinned managed queue preview.
- **Crash-resistant two-step simulation**:
  1. `PREPARED_BLOCKED` is committed to SQLite *before* any fake write;
  2. a single compare-and-swap write into the memory-only isolated
     reporting replica may occur (never into Google Sheets);
  3. a separate read compares the full immutable sanitized preview;
  4. a terminal `SIMULATED_READBACK_BLOCKED`, `CONFLICT_BLOCKED` or
     `OUTCOME_UNKNOWN_BLOCKED` event is added to the hash chain.
- A crash after PREPARE or simulated write **must not auto-retry**.
  `readback_only` permits an independently signed service to
  reconcile PREPARED or OUTCOME_UNKNOWN using **read only**, even after
  the original 45-second claim expires, provided the outbox is still
  claimed and its writer projection is still the latest. A matching
  observation moves to `SIMULATED_RECONCILED_BLOCKED`;
  a conflicting one moves to `CONFLICT_BLOCKED`.
- No step raises a real provider request or sets `READY` or
  `publish_authorized`. Existing
  `MirrorOutbox.acknowledge_external_delivery` still refuses a live ACK.

## State machine

| Operation | Prior state | New local state | Real Sheet write |
|---|---|---|---|
| PREPARE | no rehearsal | `PREPARED_BLOCKED` | None |
| Fake CAS + matching memory readback | PREPARED | `SIMULATED_READBACK_BLOCKED` | None |
| Fake response timeout or unverifiable memory readback | PREPARED | `OUTCOME_UNKNOWN_BLOCKED` | None |
| Conflicting existing replica record | PREPARED | `CONFLICT_BLOCKED` | None |
| Read-only memory reconciliation | PREPARED/UNKNOWN | `SIMULATED_RECONCILED_BLOCKED` or CONFLICT | None |

All results explicitly report:
`real_sheets_write_performed=false`,
`external_delivery_confirmed=false`,
`publish_authorized=false`,
`sheets_write_allowed=false` and
`dispatch_allowed=false`.

The successful local flag `simulated_readback_verified=true` means
**only that the in-memory copy matched.** It must not be shown to clients
as a Google Sheets success or used as a permission to post media.

## Verified offline properties

```bash
python3 scripts/test_media_mirror_rehearsal.py
python3 scripts/test_media_mirror_outbox.py
python3 scripts/test_phase5b6h_legacy_sheets_mutation_inventory.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m compileall -q src scripts
git diff --check
```

The focused suite tests service/reviewer JWT separation, invalid RSA
signatures or audience, disabled session, revoked grants, cross-account
destination, equal operational/reporting spreadsheet ID, unsafe tab,
blocked/unclaimed/expired reviewer outbox, exact CAS preview, duplicate
rehearsal refusal, old writer supersession, fail-after-write timeout,
unknown-before-write, disk failure during result journal append,
read-only recovery after the original claim expires, tampering,
and an adapter that cannot make external requests. Tests generate
ephemeral service keys and use temporary SQLite/in-memory rows only.
No real cloud credentials or spreadsheets are read or changed.

## Remaining requirements (future 5B-6J+)

1. **Real destination verification**: provision an independent Google
   service identity with destination-specific write permissions and
   confirm it has **zero write access** to operational queues. Pin the
   approved destination spreadsheet and tab in server-managed config.
   No account permissions may come from client input.
2. **Real Sheets transport with readback and retry protocol**:
   implement a separate, code-reviewed network adapter that accepts only
   a verified service execution permit, uses idempotency/version markers,
   verifies its destination before writes, performs read-before-retry
   and readback, and stores signed destination ACK. Uncertain response
   stays quarantined until independent verification.
3. **Cutover**: the 6H inventory contains 66 Python files and
   163 identified mutation calls. Individually route, restrict or
   disable the operational queue writers before designating SQLite as
   authoritative. Keep legacy behavior until a reviewed migration gate
   is satisfied; do not equate the 6H AST snapshot with runtime safety.
4. **Separate SNS publisher authorization**: even a verified Sheets
   mirror must not authorize Threads/X posting. Production media
   publication additionally needs a separate service principal,
   a server-side atomic one-use publish claim, current-rights recheck,
   unknown-outcome reconciliation, bounded egress and an approved canary.
5. **Production migration**: main branch code does not mean database
   migrations 0001–0009 have been applied on production. Backup/restore,
   IdP setup, secrets and deploy operations must go through the
   dedicated common VPS management process only.

## Scope boundary

No common VPS operations, production Google Sheets writes, live service
key provisioning, production schema migrations, SNS posting or
Cloudinary operations were performed in this development phase.
