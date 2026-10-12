# Phase 5B-6N — Dual independent operator sign-off for ONE reporting mirror PUT

**Development-only, default-disabled, not deployed.** This does not mint
operator approvals, provision Google service accounts, read any live Google
resources, update a real Sheet, migrate a live DB, or authorize an SNS post.

## Gap closed

The 6M reporting writer now requires the same credential-bound read-only
Google ACL probe immediately before its single reporting-only PUT, but an
opt-in `allow_reporting_write=True` backend could still invoke a canary
without an independently approved *specific* operation.

6N makes a **cryptographically signed, two-operator approval** a mandatory
precondition for every writer attempt. A flag, email string, existing media
review, prior ACL preflight, or approval for a different candidate is
insufficient. A 6N approval does not itself make reporting writes safe or
enable them by default.

## Code and storage

- `db/migrations/0011_sns_reporting_canary_two_operator_signoff.sql`
  creates an **append-only, local** sign-off use journal. The migration
  must only be applied by a separately approved operations procedure
  following backup/restore preparation. It has **not** been applied
  to production.
- `scripts/media_mirror_canary_approval.py` validates two
  short-lived (max 5 minutes), pinned **RS256 JWTs** with exact audience
  `sns-growth-reporting-canary-operator-approval`, token use
  `single_reporting_canary_approval`, and scope
  `mirror:reporting:canary:approve`.
- The server must be configured with **two separate, trusted operator
  public keys**, each pinned to the permitted operator identity.
  Operator keys and subjects must be distinct from one another, and
  neither RSA key can be the live Sheets service-signing key.
- Both signed approvals must bind the **exact same**
  `event_sha256`, `operation_id`, `destination_id`,
  `account_id`, `slot_id`, `queue_id`,
  `row_number`, and `projection_sha256`.
- Signatures, expiry, key/subject bindings and one-use identifiers are
  checked **after** existing 6G/6M service, session, reviewer, source,
  projection and unresolved-row checks have passed, but **before**
  any external Drive/Sheets request.
- The two approval use records and SQLite delivery
  `PREPARED_BLOCKED` event commit in **one `BEGIN IMMEDIATE`
  transaction**. Failure to store either sign-off or the PREPARED
  delivery rolls back **all three** inserts. A duplicate JWT JTI,
  changed queue/source, target mismatch or partial sign-off denies
  the attempt without any Google API call.
- Operator JWT bodies are not persisted; the SQLite journal stores
  only identity metadata and one-way SHA-256 digests of the tokens.
  Journal rows are immutable (UPDATE/DELETE triggers).

### Required operations interface (not included or enabled)

The trusted operator-signing system outside this repository must perform
real staff/owner identity authentication, enforce their scope of
authority, obtain explicit approval from two different authorized
individuals, verify that both understand the exact reporting-only
target, and issue the two JWTs separately. This code **verifies**
such statements cryptographically but does **not** implement the
human-facing approvals or prove the underlying IdP setup is sound.

The service that would invoke `deliver_once` must be controlled by
operations. The optional `as_of` parameter is an **offline test
clock injection** in current code; it must not be exposed as caller
input by any future deployed API. Real deployments also need signed
operator certificate lifecycle management, audit/alerting, restricted
network access and capability revocation.

## Runtime states

| Condition | Outcome |
|---|---|
| Reporting writer default disabled | Blocked without Google calls |
| Missing, forged, expired or single operator JWT | Blocked before PREPARED or Google calls |
| Same operator, signing key, or JTI used twice | Blocked before PREPARED |
| JWT issued for wrong event, row, account, operation or projection | Blocked before PREPARED |
| Operator signing key equals reporting service signing key | Writer enablement denied |
| One approval use fails to insert | All approvals and PREPARED roll back |
| Both approved, eligible managed queue | Sign-offs + PREPARED committed together; then existing 6M ACL checks |
| Google write result unknown | Two sign-offs stay consumed; no retry |
| Read-only reconciliation | Requires scoped service identity and current ACL, but no new write approval |

All results retain `publish_authorized=false` and
`operational_queue_modified=false`. There is no READY transition and
no SNS network permission.

## Offline validation

```bash
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

Tests use temporary signing identities, ephemeral SQLite and inert
provider facsimiles. They cover one-use and replay, mixed signers,
distinct signing key material, target drift, invalid audience/scope,
expiry, signing key rotation, signer/store faults, crash-safe atomic
rollback, ambiguous delivery and no-write reconciliation. The
existing 6M/6L test suites are rerun with the explicit two-person
test signatures; production credentials and provider data are absent.

## Remaining heavy operational tasks

1. Provision and independently manage human operator signing identities,
   approvals workflow, key rotation and two-person authorization.
2. Establish the independent reporting-only Google principal and a
   disposable reporting workbook; verify actual operational-file
   noneditability under that exact principal.
3. Through the dedicated common VPS management process, perform an
   approved backup/restore, schema migration 0011, protected public-key
   configuration, isolated dry-run and change/rollback readiness check.
4. Conduct a **real read-only** provider preflight first; any reporting
   write needs separate and explicit operator authorization plus a
   tightly supervised single-row canary.
5. Preserve legacy operational Sheets queues and production SNS media
   interlocks until the separate authority-cutover and publishing-safety
   acceptance conditions are satisfied.

The present milestone implements only the independently testable code
and is not evidence of successful real Google permissions or canary.
