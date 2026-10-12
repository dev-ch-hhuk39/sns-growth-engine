# Phase 5B-6B — Transactional publication intent journal (non-authorizing)

**Status: code-only development. No media publishing is enabled.**

## Why

Previous 5B-5A to 5B-5D review records are deliberately **not** publishing
grants. Phase 5B-6A enforces an unconditional network-level block for protected
physical-media publication. The old Google Sheets queue and the protected
SQLite review DB are independent stores, and the existing result metadata
explicitly says `publish_authorized=false` and
`external_queue_atomicity_guaranteed=false`.

This phase builds a durable, tamper-evident **intent reservation** with
duplicate detection, revocation checks and conflict quarantine, without
promoting that review into an effective publish permit.

## Changed files

- `db/migrations/0004_sns_media_publish_intents.sql`:
  dedicated intent heads + append-only hash-chain events; conservative unique
  indexes prevent reserving the same physical media ID or content hash twice
  for the same account. Unique identities remain consumed even after
  cancellation/quarantine (intentional fail-closed behavior).
- `scripts/media_publish_intent_authority.py`:
  injection-only `MediaPublishIntents` with `reserve`, `recheck`, `cancel`
  and read-only `inspect`; returns nonauthorizing status codes only.
- `scripts/test_media_publish_intent_authority.py`:
  offline RS256 signed-session and account-scope tests with temporary SQLite,
  original-proof vault bytes and fabricated server-owned operational snapshots.

## Access requirements

1. Initialize all **four** schema migrations in sequence using explicit
   trusted-operator operations, not at user request runtime. The DB connection
   requires `PRAGMA foreign_keys=ON`.
2. Verify a real server-pinned RS256 token through
   `PinnedRS256SessionVerifier` bound to the **same SQLite connection** and
   active session/account grant. Editable spreadsheet cells, unsigned
   receipts and hand-entered reviewer IDs are not credentials.
3. Use `CanonicalProtectedReviewReader`, backed by a server-owned
   operational queue/plan/receipt reader and `ProtectedEvidenceVault` on
   the **same SQLite connection**. No JSON-file or request-based source
   fallback is provided.
4. The review must already be bound to the original queue snapshot and
   independently reconciled to `MATCHED_BLOCKED`. Its review ledger
   version, reconciliation event head, queue SHA-256 and context SHA-256
   must match exactly.
5. Immediately re-evaluate the content, human-review draft chain,
   source/media binding, quality indicators, right-to-use window and
   current proof integrity/freshness. A disabled reviewer grant, explicit
   reviewer session revocation or missing trust row denies reservation.
6. The SQLite `BEGIN IMMEDIATE` transaction atomically creates the intent
   head and event, providing one-time idempotency and a defensible local
   collision barrier. It **cannot** atomically freeze Google Sheets or a
   remote SNS API response.

## States and effects

| API | Condition | Local state | External effect |
|---|---|---|---|
| `reserve` | Fresh review, source, rights and matched binding | `HELD_BLOCKED` for at most 5 minutes | None |
| `reserve` | Duplicate asset/text, revoked rights, changed queue, missing session or stale binding | Rejected; no intent written | None |
| `recheck` | Same fresh data within window | Remains `HELD_BLOCKED`; no extra event | None |
| `recheck` | Source unavailable, rights expired/revoked, mismatched content or hold expired | `QUARANTINED_BLOCKED` (permanent) | None |
| `cancel` | Authorized reviewer, exact expected intent version | `CANCELLED_BLOCKED` (permanent) | None |
| `inspect` | Read-only integrity view | `NO_INTENT` or an existing blocked state | None |

Every result exposes `publish_authorized=false` and
`effective_approval=false`. The design does not issue a bearer permit,
network-ready token, `READY` transition, real-post request or publish
credential. These states MUST NOT be interpreted as permission to loosen the
5B-6A publisher interlock.

## Important limitations

- An authenticated review **observation** and its local SQLite lock do not
  freeze external Google Sheets. A queue/rights change after the snapshot can
  occur before any later publication. Real publishing therefore remains
  permanently blocked by the 5B-6A interlock in this version.
- There is no trustable production snapshot provider, IdP login/provisioning,
  production database migration, live UI action or SNS API integration.
  Tests use locally generated ephemeral RSA keys and synthetic data.
- The content hash and media ID are intentionally unique per account across
  the entire lifetime of this first-generation journal. Cancellation does
  not free them. A future, independently reviewed repost policy would need
  an explicit, auditable new design.
- Hash-chain events detect accidental edits under normal database access;
  they are not signed or externally anchored. An attacker with full DB write
  access can attempt a coordinated rewrite. DB/OS authorization, protected
  backups and eventual external audit anchors still matter.
- Session expiry itself does not retrospectively invalidate review history;
  enabled account role and explicit session revocation are checked at intent
  reservation/recheck. A later authenticated reviewer operation still
  requires a current signed and MFA-backed session.
- Expired holds do **not** become reusable by themselves. `recheck` places
  such intents in a terminal blocked state. No retry loop, implicit lease
  stealing or silent replacement exists.
- This phase does not assert cross-queue duplicate absence in remote Sheets
  or on Threads. It protects only the local SQLite reservation set.

## Developer verification

```bash
python3 scripts/test_media_publish_intent_authority.py
python3 scripts/test_media_review_secure_console.py
python3 scripts/test_media_review_verified_adapters.py
python3 scripts/test_media_review_queue_reconciliation.py
python3 scripts/test_phase5b6a_media_runtime_interlock.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m compileall -q src scripts
git diff --check
```

## Next development stage

The missing **authoritative queue-to-publisher transaction boundary**
must be built with a server-managed canonical queue snapshot and an atomic
one-time delivery claim, including a distinct service identity, a read/write
state machine, material-rights revalidation *immediately before* a network
call, failure/timeout outcome persistence, and complete inventory of all
legacy/direct API paths. Production media publishing should be enabled only
after that boundary is proven and rolled out independently.

## Common VPS team handoff (do not execute here)

Repository: `dev-ch-hhuk39/sns-growth-engine`.

This code change requires **no immediate VPS deployment or production
migration**. Any eventual use of migration 0004 must have explicit operator
approval, a private database snapshot/restore rehearsal, isolated credentials
and disk/RAM preflight. The separate common VPS management chat owns locks,
secrets, service restarts and rollback. Never enable media posting on the
strength of a successful intent reservation, even if all GitHub CI passes.
