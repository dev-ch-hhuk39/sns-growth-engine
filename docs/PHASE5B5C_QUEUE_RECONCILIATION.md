# Phase 5B-5C — Review-to-queue binding and conservative reconciliation

## Delivered scope: atomic within the dedicated SQLite review DB

The existing 5B-5A review ledger is retained, and 5B-5B identity and
protected-proof adapters are reused. This phase adds a **local, opt-in,
fail-closed queue binding and read-only reconciliation protocol**. It does not
make Google Sheets + SQLite one atomic transaction.

- `db/migrations/0003_sns_media_review_queue_reconciliation.sql`: local
  queue/ledger binding row plus append-only, hash-linked reconciliation events.
  Migration requires the existing 0001 review tables. It has no
  approval/POSTED/publish-authorizing state.
- `scripts/media_review_queue_reconciliation.py`: a guarded in-transaction
  adapter, full queue/content and review-proof fingerprinting, stale-revision
  detection, bounded recurring reconciliation queue, quarantine, and a
  read-only nonauthorizing barrier.
- `media_review_trusted_precommit.py`: optional complete queue SHA-256 on a
  review request and a bounded deterministic fingerprint of plan, receipts,
  and proof metadata. Guarded 5B-5C records REQUIRE the expected complete
  queue fingerprint; a queue change with an unchanged revision is blocked.
- `media_review_transactional_ledger.py`: **optional** `queue_authority`
  parameter for review/revocation, invoked after the ledger append and
  before SQLite commit. A mismatch or journal-write error rolls back both.
  The original 5B-5A unguarded ledger API remains intentionally isolated,
  and its result is never effective approval.
- `scripts/test_media_review_queue_reconciliation.py`: in-memory and
  two-connection tests covering atomic rollback, CAS, operation replay,
  unchanged queue vs changed caption or source, original-proof revocation,
  stale proof verification, reviewer receipt drift, legacy unbound revocation,
  record tampering, unavailable source and all-bad outcomes.

## State contract

Every state is nonauthorizing:

| State | Meaning |
|---|---|
| `NO_BINDING` | No locally bound review |
| `REVIEW_RECORDED_BLOCKED / PENDING` | Review and queue snapshot bound in one SQLite commit; external consistency not checked |
| `REVIEW_RECORDED_BLOCKED / MATCHED_BLOCKED` | One *historical* read matched queue and current rights; still not publishable |
| `DRIFT_QUARANTINED / CONFLICT_BLOCKED` | Source changed, ledger drifted, proof revoked/expired, or source unavailable |
| `REVOKED_BLOCKED / CONFLICT_BLOCKED` | An authorized revocation recorded; remains blocked |
| `LEDGER_DIVERGENCE_BLOCKED` | Read-only barrier detected unbound later legacy ledger changes |

A matched row stays in `pending_candidates()` for further rechecks.
Repeated unchanged matches do not append new journal entries indefinitely; a
new drift, revocation or first match is recorded.
Once quarantined it **cannot be automatically unquarantined** if Sheets later
matches again. Explicit revocation and a fresh reviewed draft/queue binding
would be needed. The code does NOT schedule a polling service.

The canonical review context is hashed, including plan, complete receipts and
evidence metadata. Its original evidence is revalidated against rights scope,
usage, expiration, verification freshness, source, asset and queue at each
reconciliation. Only hashes and immutable IDs are stored in the journal; raw
captions, media content, bearer tokens and private proof text are not.

## What is NOT solved

1. **External atomicity.** Google Sheets does not participate in the SQLite
   transaction. A Sheets edit may race with or occur after the last observed
   snapshot. CAS and the journal apply only to the SQLite side. A successful
   `MATCHED_BLOCKED` is not a live lock on the external row.
2. **Live backend provisioning.** The repository still lacks a deployed,
   server-controlled canonical queue snapshot reader, IdP session backend,
   protected proof-storage volume and trusted human-review endpoint. Offline
   test fakes do not make external identity/evidence integration complete.
3. **Runtime enforcement.** Existing Sheet-based READY writers, pending
   posting jobs, workers and publish-time final authorization have not been
   changed or activated in this phase. A future rollout must move the
   **publication authorization source of truth** to one atomic datastore,
   or enforce a tested and comprehensive external consistency protocol,
   including all legacy and scheduler paths. Until then, approval is disabled.
4. **Recoverability and operations.** There is no production migration,
   backup/restoration verification, monitoring worker, external hash anchoring
   or live posting evidence from this source-only development.

Every new result retains
`effective_approval=false`, `publish_authorized=false`,
`ready_transitions_performed=false`, and
`external_queue_atomicity_guaranteed=false`. A review transaction cannot
make an external queue READY, enable X, or publish any content.

## Developer verification

```bash
python3 scripts/test_media_review_queue_reconciliation.py
python3 scripts/test_media_review_transactional_ledger.py
python3 scripts/test_media_review_trusted_precommit.py
python3 scripts/test_media_review_verified_adapters.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m compileall -q src scripts
git diff --check
```

External service integration is deliberately not in these tests.

## Phase 5B-5D / 5B-6 follow-up

1. Develop a protected reviewer UI/API wired to real IdP sessions and
   original proof; use exact queue SHA and expected revision.
2. Implement a single atomic publication authority for READY eligibility
   (recommended: dedicated DB owned by review + queue + publisher).
   Preserve Sheets as a nonauthorizing read-only/projection UI during migration.
3. Enumerate and guard **every** old Sheets/CLI/manual/autonomous READY
   transition and every actual publisher entrypoint. Maintain kill switch,
   correct account, media/proof and duplicate checks.
4. At actual publish time, re-read proof, reviewer authorization state,
   queue and ledger, enforce a source revision/fingerprint gate, and fail
   closed when external snapshots disagree.
5. Demonstrate real rollout, staged canary, read-after-write and post
   reconciliation under VPS management. Do not claim completion from mocks.

## VPS management handoff — do not run from this development chat

- Tool: SNS Growth Engine, repository: `dev-ch-hhuk39/sns-growth-engine`.
- Commit: use exact **merged** SHA only after full GitHub CI PASS.
- No immediate deployment or production DB migration is required by this
  source-only PR. If future rollout is authorized, migrate 0001/0002/0003
  only within the dedicated protected SNS review DB, using a tested backup
  and rollback that **preserves all append-only events**.
- Preflight: check common deploy lock
  `/run/lock/chadult-production-deploy.lock` and current shared VPS
  disk/RAM policy with VPS management; avoid interfering with other
  applications, services or runners.
- Validate DB FK, triggers, CAS, forged/revoked source denial and
  recovery on a disposable copy. Record exact installed and recovery
  revisions. Never equate a DB schema being installed to being authorized
  to publish.
