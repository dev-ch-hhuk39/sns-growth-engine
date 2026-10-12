# Phase 5B-6F — Managed SQLite queue commands and read-only Sheets preview

**Development code only. This is not a production queue cutover or an actual
Google Sheets synchronization. Protected media remains unpublishable.**

## Implemented

Migration `0007_sns_managed_queue_writer.sql` creates a managed queue
command head, immutable hash-chained command events, and an append-only
read-only mirror-preview journal in the **same private SQLite DB** as
migrations 0001–0006.

`scripts/media_managed_queue_writer.py` provides:

- `MediaManagedQueueWriter.bind` — one-time authenticated binding of a
  fresh protected shadow queue. Requires a verified scoped RS256 reviewer,
  active MFA-backed revocable session, original proof vault and exact
  `SQLiteShadowOperationalSnapshot` from **the same DB**. The draft,
  account, asset/rights proof and queue are validated via the existing
  canonical reader. Binding must happen **before** any review, reconciliation,
  intent or dispatch event. Client JSON and outside Sheets rows cannot
  impersonate this trusted source.
- `transition` — signed reviewer + CAS command `HOLD`, `ARCHIVE` or
  `QUARANTINE`. Only nonpublishing states exist. An archived/quarantined
  candidate cannot be resumed or silently rebound. All transitions atomically
  append a tamper-detectable event plus a sanitized preview record.
- `reconcile_observation` — after an independently verified matching
  6E shadow `OBSERVE` event, the writer explicitly advances its pinned
  shadow event/version using a new signed command and optimistic CAS.
  It rejects a `REFRESH`, missing history, changed content/proof or
  source failure; managed readers fail closed until successful reconciliation.
- `SQLiteManagedOperationalSnapshot` — **opt-in** backend reader for
  the existing protected `CanonicalProtectedReviewReader`. It accepts
  only `MANAGED_BLOCKED` with a valid audit chain and exactly matching
  shadow event/queue identity, then performs the earlier 6E 90-second
  freshness/rights verification on the same connection. This is the
  intended adapter for future controlled review/intent/dispatch.
- `mirror_previews` — read-only **last event per queue** projections:
  account, slot and queue IDs, state, CAS version, hashes and explicit
  `publish_authorized=false`, `view_only=true`. No captions, media
  URLs, tokens, original evidence, delivery/ACK flag, write credentials or
  real Sheets transport are present. They are *preview data*, not
  automatically delivered Sheets rows.

The previous 6E `_may_refresh` path now also refuses all shadow
content refreshes once a managed queue binding exists. New matching source
observations can still be recorded, then must be explicitly reconciled
by the managed writer. This avoids silently substituting changed captions
under an already-bound managed record.

## State machine

| Operation | From | To | External effect |
|---|---|---|---|
| BIND | no managed head, fresh 6E shadow | `MANAGED_BLOCKED` | None |
| RECONCILE | MANAGED, newer exact-match 6E OBSERVE | `MANAGED_BLOCKED` | None |
| HOLD | MANAGED | `HOLD_BLOCKED` | None |
| ARCHIVE | MANAGED or HOLD | `ARCHIVED_BLOCKED` | None |
| QUARANTINE | MANAGED or HOLD | `CONFLICT_BLOCKED` | None |

All results report `publish_authorized=false`,
`dispatch_allowed=false`, `sheets_write_allowed=false`,
`mirror_published=false` and
`external_queue_atomicity_guaranteed=false`. The real Threads/X media
network interlock from 5B-6A is untouched. No operation promotes to
`READY`, sends a post, or changes production Sheets.

## How the private, development-only queue is read

```python
private_reader = CanonicalProtectedReviewReader(
    source=SQLiteManagedOperationalSnapshot(
        db=db, vault=ProtectedEvidenceVault(db)
    ),
    vault=ProtectedEvidenceVault(db),
)
# Explicit backend binding and a permitted MANAGED_BLOCKED state are
# required before this reader can fetch queue data for review/intent/dispatch.
```

The bootstrap shadow reader from 6E remains available for earlier tests and
explicit shadow capture. **Production code is not yet switched** to the
managed adapter; current legacy writer/reader routes therefore still exist.
No server-side router enforcing this adapter across *all* writes is claimed.
Migration 0007 is not applied to any production database.

## Tests

`scripts/test_media_managed_queue_writer.py` uses ephemeral RSA keys,
temporary SQLite database, fake server-owned source and synthetic protected
proofs. It includes all inherited 6E tests and additional checks for:

- Invalid signer, audience, account, operation and source type.
- Missing/stale/revoked source, proof, reviewer and expired observation lease.
- Review/intent/dispatch can run from the managed read adapter.
- Old-version CAS, duplicate operations and simultaneous DB connections.
- Fail-injected mirror insert rolls back both head and event atomically.
- Append-only events, mirror tampering detection and only-latest projection.
- Safe HOLD/ARCHIVE, no reopen and managed-reader blocking.
- Independently observed identical shadow content requiring explicit
  reconcile, changed content causing permanent quarantine instead.
- No real Sheets writer, external SNS API or live credentials in the module.

```bash
python3 scripts/test_media_managed_queue_writer.py
python3 scripts/test_media_shadow_queue_authority.py
python3 scripts/test_phase5b6d_network_sink_inventory.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m compileall -q src scripts
git diff --check
```

## What remains: 6G and deployment gates

1. **Separate live publisher service identity:** reviewer credentials
   cannot grant SNS execution. Establish trusted server-side service
   principal with independently verified publication authorization and
   revocable delivery claims before enabling media network access.
2. **Canonical writer cutover:** the operating queue is still in Sheets.
   Audit *all* legacy reads/writes and switch them to a server-managed
   queue with a single transactional operational backend. Then Sheets
   becomes an asynchronously updated read-only projection. This phase
   creates only the sanitized preview and does not call Sheets.
3. **Mirror transport and delivery confirmation:** a permission-isolated
   service may later transport vetted projections with idempotent ACK,
   source hashes, retry limits and conflict reconciliation. This PR has
   no transport, ACK or external write.
4. **External exactly-once semantics:** SNS APIs cannot join the SQLite
   transaction; verified outcome-uncertain handling, network egress
   controls, monitoring and rollback remain required.
5. **Production verification:** live IdP integration, private DB migration
   backup/restore, cross-store drift canary, service security review,
   limited rollout and production evidence remain unimplemented.

**Dedicated common VPS handoff:** do not deploy or migrate from this
development chat. Only the separate common VPS management chat may operate
production SSH, deploy locks, backups, databases, jobs, service restarts
and rollback. No VPS or SNS posting was performed here.
