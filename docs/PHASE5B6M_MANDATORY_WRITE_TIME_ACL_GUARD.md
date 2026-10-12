# Phase 5B-6M — Mandatory provider ACL gate at reporting write time

**Code implementation only. No real Google provider access, production
migrations, VPS changes, SNS posting or production Sheets writes.**

## Why this phase was necessary

Phases 6K/6L introduced a separate, opt-in Drive/Sheets metadata reader
and an isolated read-only canary. However, Phase 6J's reporting-only
`IsolatedSheetsMirrorDelivery` was not required to call that reader before
the actual `values.update`. An independently green preflight could
become stale, or the write engine could be enabled with an unbound
worksheet. That gap had to be closed **before** even considering an
explicitly approved reporting-only pilot.

## Implemented changes

### 1. Single principal, no unbound worksheet loophole

The 6J `GspreadReportingFixedRow.from_trusted_client` factory now marks
the adapter as credential-bound and retains its exact `client.auth`
object reference. A directly constructed worksheet stays unbound.

An `IsolatedSheetsMirrorDelivery` can still be constructed with
`allow_reporting_write=False` by default. If a trusted caller elects
`allow_reporting_write=True`, its constructor now refuses to proceed
unless ALL conditions hold:

- `acl_metadata` is a trusted `ReadOnlyGoogleMirrorMetadata` instance.
- The reporting adapter is a factory-bound `GspreadReportingFixedRow`.
- The adapter and ACL metadata reader hold the **same credential object**.
- The pinned expected principal email matches the metadata credential.
- Existing dedicated RS256 service, destination, row, reviewer/outbox
  lease, and current queue requirements remain unchanged.

This validation cannot be replaced with an untrusted boolean supplied
by a caller or a different credential object with the same email.
No fallback to a direct worksheet is available for enabled delivery.

### 2. Actual write flow performs fresh provider checks

After committing the durable SQLite `PREPARED_BLOCKED` event, before
reading the reporting row, the engine performs the three bounded,
read-only 6K provider metadata GETs:

1. Confirm the **operational spreadsheet** cannot be edited or
   modified by the current service principal.
2. Confirm the separately pinned reporting spreadsheet is editable
   and its content is modifiable by that principal.
3. Confirm the exact reporting spreadsheet ID and pinned tab identity
   and grid shape.

The same mandatory checks run **again immediately before the sole
reporting-only PUT**, after the engine has inspected the destination's
current row. At the same point, the JWT/session, reviewer claim, and
pinned managed-queue preview are revalidated.

The checks also run before a 6J **read-only recovery** operation can
mark an unknown result reconciled. An unproven or newly unsafe ACL
cannot lead to a claimed successful reconciliation.

Passing a capability inspection remains only a current observation.
No Google Sheets API operation is made atomic with SQLite; provider
ACLs can still change between GET and PUT. A real deployment must
separately isolate service credentials, restrict network access,
protect the reporting destination from other editors, use a dedicated
operator-approved canary, and monitor ACL drift.

### 3. Fail closed, preserve uncertain outcomes

A failed metadata GET, missing Drive capability, wrong credential
binding, unexpected tab, permission change, revoked service session or
stale review stops the reporting update.

Because `PREPARED_BLOCKED` has already been committed, an error
between checks and a possible PUT is recorded in the append-only
journal as `OUTCOME_UNKNOWN_BLOCKED`. This is deliberately conservative.
The engine never attempts an automatic second PUT and never permits
a later queue revision to leapfrog an unresolved report attempt.

All returned authority fields remain:
`publish_authorized=false`,
`operational_queue_modified=false`,
`dispatch_allowed=false`.
The existing media posting interlock is unchanged.

## Offline acceptance tests

`scripts/test_media_mirror_write_acl_gate.py` inherits the existing 6J
tests and adds failures for missing metadata, mismatched service
credentials, unbound worksheet, edited operational file, missing
reporting edit permission, provider outage, revoked principal and
permission changes between the initial row GET and final PUT.

The same synthetic session is used to assert that six Drive/Sheets
metadata GET calls (two full checks) precede a successful one-time
reporting PUT. Read-only reconciliation is denied if operational edit
rights appear after a previously uncertain delivery.

Existing synthetic tests for 6J and 6L have been adjusted to use the
new shared credential binding; assertions and safety conditions have
not been weakened.

```bash
python3 scripts/test_media_mirror_write_acl_gate.py
python3 scripts/test_media_mirror_readonly_canary.py
python3 scripts/test_media_mirror_reporting_delivery.py
python3 scripts/test_phase5b6h_legacy_sheets_mutation_inventory.py
python3 scripts/test_phase5b6d_network_sink_inventory.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m compileall -q src scripts
git diff --check
```

All synthetic calls operate on temporary SQLite and local in-memory
provider fixtures. Neither a service-account credential file nor a
live Google spreadsheet was accessed.

## Remaining heavy work: Phase 5B-6N and later

- Independently provision a reporting-only Google service identity,
  and explicitly check actual Drive file capabilities and tab
  protection under that identity. This requires operational approval.
- Select a disposable reporting workbook and one pre-provisioned row.
  Confirm the operational workbook is not editable by the mirror service,
  including external group/share paths.
- Through the separate shared-VPS operations process, prepare backups,
  reviewed migration 0010, service identity ownership, secret handling,
  production change controls, rollback and monitoring.
- First run a **real read-only** provider check. A limited reporting
  write requires a second, separate approval and a canary with human
  inspection and unknown-outcome recovery.
- Independently route legacy Sheets queue writers to the authoritative
  backend, and design separate one-use SNS publishing authorization.
  Neither phase 6M nor a later reporting mirror success unlocks SNS.
