# Phase 5B-5A — Transactional Media Review Ledger (development only)

## What is implemented

This phase introduces an **isolated SQLite review ledger** with transactionally
consistent append-only review/revocation events. It is not an authorization
service and is not connected to the operational Google Sheets posting queue.

Files:

- `db/migrations/0001_sns_media_review_ledger.sql`: review head, immutable
  event records, unique operation IDs, version checks, FK and append-only triggers.
- `scripts/media_review_transactional_ledger.py`: explicit migration function,
  precommit-checked decision recording, independently authenticated revocation,
  chain verification, optimistic expected-version check and safe rollback.
- `scripts/test_media_review_transactional_ledger.py`: tests for revisions,
  corrupt head binding, unauthorized sessions, expired rights, replay, injected
  database failures, revocation, external tampering and two DB connections.

**No migration or deployment was executed on the shared VPS.** This is
source-controlled architecture and offline test coverage, not a live DB.

## Critical trust boundaries

1. Calls to `record_review` require a real `SessionVerifier` and
   `CanonicalReviewReader` supplied by the trusted backend. Those providers
   remain **unimplemented** in this repo. Without them, the operation fails.
   Tests use in-memory fakes; they cannot be used as production providers.
2. The 5B-4A `evaluate_precommit` check is performed within the SQLite
   transaction before the ledger append. The SQLite head CAS and event insert
   are committed or rolled back together (`BEGIN IMMEDIATE`). An external
   Google Sheets queue is **not** in this same transaction. A Sheets update
   racing with a review is not prevented by this isolated DB.
3. A successful record is `ISOLATED_REVIEW_LEDGER_RECORDED_NOT_AUTHORIZED`.
   The response explicitly declares:
   `authenticated_approval_integrated=false`,
   `external_queue_atomicity_guaranteed=false`,
   `effective_approval=false`, `ready_transitions_performed=false`,
   `publish_authorized=false`. No queue or publisher is invoked.
4. Revocation requires a fresh, MFA-verified reviewer with account scope
   and the exact previous review fingerprint and expected version. Revocation
   can still be recorded after underlying rights have expired; no active
   review can be reused after a revocation with the same draft fingerprint.
5. Event hashes and database triggers can detect accidental tampering.
   **Neither provides cryptographic authentication or external tamper
   resistance**. A privileged DB administrator could change the entire
   history; production would need protected backups and external head
   anchoring / audit exports.

## Safety / storage characteristics

- Review events only hold normalized identifiers, hashes, decision kind,
  expiry timestamp, reviewer subject and operation ID. No bearer token,
  captions, media URLs, original evidence text or API credentials are stored.
- Each candidate's immutable history is bounded to 512 events; when full,
  write operations fail closed. Do not delete historical events to free space.
- The code expects SQLite foreign keys enabled, an autocommit connection
  outside an existing transaction, and an explicitly migrated schema.
- A unique operation ID prevents accidental duplicate appends; a stale
  `expected_ledger_version` fails before writing. The app never silently
  overwrites previous approval history.
- SQLite protects only its own database; for any production deployment,
  restrict DB file access, choose a secure storage volume, define backup
  encryption, test restore, and monitor WAL/journal retention.

## Standalone offline test

```bash
python3 scripts/test_media_review_transactional_ledger.py
```

The regression suite uses `sqlite3.connect(':memory:', isolation_level=None)`
and separately tests a temporary file with two connections. No real identity
provider, Google Sheets access, disk migration on the shared VPS or publishing
operation is performed. Full repository CI must also pass.

## Migration / operations handoff (do NOT execute from this chat)

**Tool:** SNS Growth Engine

**Repository:** `dev-ch-hhuk39/sns-growth-engine`

**Commit:** Use the exact merged commit SHA after PR CI/merge; do not deploy
unmerged feature branches to the shared VPS.

**Purpose:** Prepare an isolated protected review ledger for a future
authenticated approval service. This source-only PR does not require
any immediate VPS deployment or DB migration.

**Future operations (VPS management chat only):** Choose an approved
data-store location, enforce ownership/0600 file and private directory,
back up the database and original config, apply the migration only against
the dedicated SNS review database, prove restore on a disposable copy,
verify FK/triggers and integrity, and record an exact rollback procedure.

**Required disk/RAM:** migration itself is tiny but must pass
`sudo -n /usr/local/sbin/chadult-vps-resource-check --preflight 8`
and the shared deploy lock policy before any future production installation.
Full application deployment size must be measured then; do not presume
database DDL alone is adequate for a release.

**Health and rollback:** Verify database open/read, schema version, unique
op constraints, append-only triggers and simulated faulty transaction
rollback. If release health fails, restore the previous application;
never discard the newly created review event ledger or overwrite backups.
Do not attempt live restore tests in this development chat.

## Next heavy phase

5B-5B: Implement a verified identity adapter and secure role/account mapping
(MFA proof must come from trusted IdP claims or an equivalent session store),
a protected evidence repository and permission provenance, and plan the
authoritative Sheets-to-review-DB reconciliation. Formal approval must
remain disabled until there is one canonical store or a tested cross-system
consistency protocol. Only after this may older Sheets READY writers
and the publisher be migrated to enforce authority / rights revalidation.
