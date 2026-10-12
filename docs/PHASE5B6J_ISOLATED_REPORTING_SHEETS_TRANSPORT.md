# Phase 5B-6J — Opt-in fixed-row Google Sheets reporting mirror transport

**Status: GitHub development code only. NOT enabled in runtime, NOT deployed,
NOT a successful live Google Sheets synchronization, and NOT a media publisher.**

## Decision: report-only Sheets transport, not a production queue cutover

Phase 5B-6I verifies a separate reviewer-vs-service identity and simulates
readback against an in-memory replica. Phase 6J adds a narrowly bounded
real gspread `Worksheet.update` *implementation* and a protective SQLite
audit protocol, but **does not** connect a real service credential or
execute a live write.

Google Sheets `values.update` updates a selected range with `RAW`
values. Unlike SQLite transactions, it cannot atomically coordinate a
conditional compare-and-swap with the protected SQLite database or with
other Sheets editors. This implementation is therefore only a reporting
mirror, never the operational queue or a SNS publication authorizer.
Its old-value read protects against many stale writes but does not
eliminate cross-store races or concurrent edits by another principal.

Official interface documentation:
- https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/update
- https://docs.gspread.org/en/v6.2.1/api/models/worksheet.html

## Files

- `db/migrations/0010_sns_mirror_reporting_delivery.sql`: explicit
  migration after 0001–0009 for service sessions (default disabled),
  destination policy (default disabled), immutable row mapping, delivery
  heads and append-only, hash-chained events.
- `scripts/media_mirror_delivery_identity.py`: independent pinned RS256
  service authentication with `aud=sns-growth-mirror-reporting-write`,
  `scope=mirror:reporting:write` and
  `token_use=mirror_reporting_live`. Requires an unrevoked, enabled,
  server-provisioned token/session fingerprint and destination/account
  mapping. Neither reviewer JWT nor 6I rehearsal JWT may be used.
- `scripts/media_mirror_sheets_adapter.py`: tiny gspread adapter. It
  can **only** read the exact pinned reporting worksheet header and a
  pre-provisioned `A<row>:L<row>` range, or issue one named
  `worksheet.update(range_name=..., values=[...], value_input_option="RAW")`
  to the same row. Never creates, inserts, appends or searches rows.
  Rejects a worksheet with unexpected spreadsheet ID, tab title,
  dimensions, untrusted header, malformed row, wrong metadata, formulas
  or a failed SHA-256 projection checksum. The 12 columns contain only
  schema, candidate IDs, version, hashes, blocked state and non-publish
  flags, not source text/media/rights originals/secret tokens.
- `scripts/media_mirror_reporting_delivery.py`: opt-in delivery
  orchestrator, **`allow_reporting_write=False` by default**, with no
  CLI, HTTP endpoint, scheduler, environment toggle, Google credential
  bootstrap or runtime hook. An operator must provision a separate,
  least-privilege gspread client and explicitly construct this backend
  after a separate approval/ACL review; this PR does not do so.
  Requires a currently claimed 6G outbox, its valid 45-second lease,
  a current 6F managed-queue projection, 6J live service identity and
  an exact matching pinned fixed-row adapter.
- `scripts/test_media_mirror_reporting_delivery.py`: ephemeral RSA,
  temp SQLite and fake gspread-compatible worksheet. No real API call.

## Transaction and failure protocol

| Event | SQLite audit state | Provider write? |
|---|---|---|
| One-time verified service claim | `PREPARED_BLOCKED` committed first | Not yet |
| Row already equals current sanitized preview | `READBACK_VERIFIED_BLOCKED` | None |
| Valid empty or older same-candidate row | PREPARED, then one bounded RAW PUT and a new read | **One only, if operator explicitly enabled** |
| Exact post-write readback | `READBACK_VERIFIED_BLOCKED` | No further writes |
| Conflicting row (other queue, equal/newer revision) | `CONFLICT_BLOCKED` | None |
| Timeout, bad response, inability to inspect | `OUTCOME_UNKNOWN_BLOCKED` | Never retry automatically |
| Crash after PREPARED or write | PREPARED persists | Never retry automatically |
| Read-only reconciliation of PREPARED/UNKNOWN | `RECONCILED_BLOCKED` if matched; otherwise remain blocked/conflict | **None** |

Only one unresolved PREPARED, UNKNOWN or CONFLICT writer is allowed for a
pre-provisioned destination/row at a time. Changes to mapped rows are
forbidden; a second SQLite connection cannot replay the same delivery.

No code path silently promotes to `READY`, dispatch, media posting or
modifies the operational queue. All response contracts include
`publish_authorized=false` and `operational_queue_modified=false`.
A `READBACK_VERIFIED_BLOCKED` state attests to a matched reporting
row via the injected adapter, *not* to approved publication, complete
provider ACL verification, or external exactly-once guarantees.

## Static legacy writer inventory review

Phase 6H's AST manifest is deliberately updated from
**66 files / 163 mutation call sites** to
**67 files / 164 call sites**, adding exactly one reviewed
`scripts/media_mirror_sheets_adapter.py: worksheet.update` call.
The new call lives behind a dedicated service identity, immutable row
mapping, PREPARED journal and disabled-by-default backend. It is not
a blanket approval for any old queue writer. The 6H CI baseline remains
active to surface new unreviewed mutators.

## Test commands

```bash
python3 scripts/test_media_mirror_reporting_delivery.py
python3 scripts/test_phase5b6h_legacy_sheets_mutation_inventory.py
python3 scripts/test_media_mirror_rehearsal.py
python3 scripts/test_media_mirror_outbox.py
python3 scripts/test_phase5b6d_network_sink_inventory.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m compileall -q src scripts
git diff --check
```

## Known limitations / next stage

1. **No real credentials, target ACL, or network proof.** The policy checks
   distinct IDs and pinned tab/row locally. The deployment process must
   independently prove the service account has *no write permission* to
   operational Sheets, audit destination ownership/ACL and activate the
   safe reporting destination after explicit approval.
2. **Not an atomic provider CAS**. No Google Sheets values.update
   transaction can join SQLite's `BEGIN IMMEDIATE`. A single isolated
   service writer, ACL enforcement and protection from external editors
   are required before any live canary. Unknown responses may reflect
   an applied update; only readback can reconcile, never blind retries.
3. **No background worker/execution API**. Code is not wired to runtime
   job routing, service identity provisioning, or Google login. New
   database migration 0010 is **not applied in production**.
4. **Operational cutover not done**. 6H shows 67 files/164 calls in the
   codebase, not all of which are media queue writers. They need
   per-callsite ownership/classification and a phased operational queue
   backend migration before SQLite can become authoritative.
5. **SNS media posts remain stopped**. Phase 5B-6A direct Threads/X
   media network interlocks are unchanged. Neither any Sheets mirror
   success nor any reviewer or mirror service token grants SNS posting.
6. **VPS operations are separate**. Any approved canary, service ACL,
   secrets, migration 0010, backup/restore, deploy/rollback and alerting
   must be executed only by the dedicated common VPS management chat.
   Nothing on production was touched by this development phase.
