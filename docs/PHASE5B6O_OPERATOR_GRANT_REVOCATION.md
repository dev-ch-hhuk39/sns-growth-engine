# Phase 5B-6O — Current human authorization grants and pre-PUT revocation guard

**Source-code milestone only. No live Google/Drive/Sheets access, OAuth
provisioning, shared VPS operations, production schema migration, or SNS posts.**

## Why Phase 6O is required

Phase 6N verified two independent, pinned operator signatures for exactly
one reporting-mirror operation. Valid cryptographic signatures alone do
not establish that a human remains authorized for that account and
destination. A revoked former approver could otherwise present a signed
JWT within its remaining lifetime.

6O adds a second, server-owned current-authorization registry and checks
it **both before committing a delivery PREPARED record and again
immediately before the single permitted reporting-only PUT**.

## Implemented

- `db/migrations/0012_sns_canary_operator_grants.sql`:
  a manually provisioned, default-disabled table of exact
  `signer_kid`, `signer_subject`, `account_id`,
  `destination_id`, and one of two `approval_slot` roles.
  No wildcard grants or runtime self-registration exist.
- Each grant carries a bounded `valid_from` / `valid_until`, an
  `enabled` switch, `revoked_at`, `grant_generation`, and
  `provisioned_by`. The table forbids row deletion or changing
  the configured key/subject/account/destination/slot.
- A grant cannot be reenabled after revocation/disablement without
  increasing its generation. Earlier operator JWTs remain unusable
  even if a new grant period is authorized for the same identity.
- `scripts/media_mirror_operator_grants.py` requires an exact
  active, unrevoked grant in the **same private SQLite transaction**
  where the two operator JWTs are inspected. The JWT additionally
  has to bind the expected `approval_slot` and current
  `grant_generation`. Signatures issued before grant activation,
  expiring after the grant ends, wrong scope, absent/malformed/expired
  grants, and mismatched generations are rejected.
- `scripts/media_mirror_canary_approval.py` retains the two
  independent pinned RS256 human-signature and exact-target checks
  from 6N, and now verifies their current server-owned grants.
- `scripts/media_mirror_reporting_delivery.py` adds a **fresh
  before-PUT** validation of both original consumed sign-off tokens,
  exact operation/event/projection and current operator grants.
  It runs in a consistent short SQLite read transaction, after the
  second 6M Drive/Sheets ACL recheck and before the sole Google
  reporting-row PUT. With a real clock, the signing time and service
  outbox lease are sampled again before the write; the existing
  `as_of` override is an *offline-test-only* injectable clock.
- If a signer becomes revoked or loses authorization between the
  first PREPARED commit and the last provider GET, the attempted
  reporting PUT does **not** take place. The already durable
  receipt remains `OUTCOME_UNKNOWN_BLOCKED`, and **no automatic
  retry or renewed authorization** is attempted.
- Existing read-only reconciliation remains available after an
  operator's later revocation, provided its separate service/session,
  ACL, signed queue and current source checks all succeed.
  Reconciliation does not issue a new PUT.

All gates are supplemental. They cannot enable SNS media publication,
claim external Sheets confirmation, promote queue items to READY,
change the operational Sheet, or override the default disabled state.

## Explicit security boundaries

An operator grant is trusted only when independently provisioned by
a privileged operations process; copying a row from Sheets or trusting
a claimed name does not authorize anyone. This phase does not provide
staff login, a human approval UI, an IdP integration or operator
signing credentials. An external, independently reviewed approver
system must authenticate and record two actual authorized people.

SQLite transactions cannot be made atomic with Google Sheets
`values.update`. A grant or Drive ACL may still change in the
small gap after the final recheck and before a provider PUT.
Mitigations for a real canary include a separate service account
without operational write permission, restricted reporting-only
destination, approved canary window, zero competing writers,
monitoring, and stop/rollback procedures. None are activated by
this code merge.

For production, the test-only `as_of` parameter must never be
accepted from an untrusted request or public endpoint. JWT issuance
and safe distribution, pin lifecycle, key rotation and the operator
grant table provisioning remain operations tasks.

## Tests

```bash
python3 scripts/test_media_mirror_operator_grants.py
python3 scripts/test_media_mirror_canary_approval.py
python3 scripts/test_media_mirror_write_acl_gate.py
python3 scripts/test_media_mirror_readonly_canary.py
python3 scripts/test_phase5b6h_legacy_sheets_mutation_inventory.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m compileall -q src scripts
git diff --check
```

The new synthetic coverage tests omitted and disabled grants, revocation,
grant-period boundaries, changed epochs, immutable policy scope,
role order, wrong account or destination, reenablement requiring
new generation, and a revoke precisely between the two ACL probes
and the attempted provider PUT. All use temporary SQLite, in-memory
Google response facsimiles and test-only signing identities.

## Remaining stages

1. Trusted two-person identity/approval issuance system, ownership,
   operator pin/role and grant provisioning, revocation runbook.
2. Separate Google Workspace reporting-only principal and isolated
   writable workbook; inspect real scopes and ACLs without modifying
   either workbook before any write approval.
3. Production backup/restore, approved migrations 0010–0012, key
   rotation, service account secrets, network controls and canary
   incident procedures via the dedicated common VPS operations chat.
4. One separately approved disposable-row reporting-only write,
   readback, no-retry after uncertainty and independent verification.
5. Distinct operational queue source cutover and **separate** SNS media
   publish authorization; mirror reports never grant publish access.
