# Phase 5B-5D — Protected reviewer console and operation interface

## Delivered (source-only; production deployment is **not** complete)

This phase extends the Phase 5B-5A/5B-5B/5B-5C nonauthorizing review stack with
an **injection-only, WSGI-compatible server-rendered UI/operation adapter**.
The code does NOT launch a server, bootstrap IdP users, configure sessions,
allow READY writes, approve publishing, upload media, or execute posts.

Files:

- `scripts/media_review_secure_console.py`: `ProtectedReviewConsole`,
  a WSGI callable with no default runtime configuration, identity provider,
  trusted queue reader, HTTP server, session cookie issuer or credentials.
- `scripts/media_review_protected_evidence.py`: adds scoped, authenticated,
  freshness-checked original-proof retrieval. Existing immutable events,
  revocation checks, original SHA-256 verification and account/slot/queue
  identity binding remain required.
- `scripts/test_media_review_secure_console.py`: uses temporary SQLite,
  ephemeral RSA key pairs and fake server-owned operational snapshots to
  exercise the UI and security contract end to end. No actual IdP, production
  browser, Google Sheets, posting API, or protected production DB is accessed.

## What a trusted operator could use once provisioned

1. Open `/review?account=liver_manager` (or an account with a valid review
   role). Only server-owned inbox keys and already recorded local reviews for
   the authenticated account are shown.
2. Inspect candidate IDs, current review state, queue revision and proof kinds.
   Use **投稿文を確認** to view exact current candidate text as `text/plain`.
   Use **証跡原本を取得** to request the original file only after independent
   session, CSRF, account and exact source-asset-evidence binding checks.
3. Check the confirmation box and choose **台帳に記録** only for a valid,
   fresh APPROVE draft already bound to the same authenticated reviewer,
   current plan/receipts, queue content, protected rights and quality checks.
   A successful result is an isolated review record with a simultaneous
   SQLite-only queue binding, **not** an effective approval or READY transition.
4. Choose **レビュー記録を取消** with an enumerated reason. It checks the exact
   expected ledger version/head hash and authenticated reviewer permission,
   then revokes the review and its SQLite binding in a single transaction.
   Cancellation is still available when the external source/inbox disappears,
   but new approvals are not accepted without that source.

HTML does not embed bearer tokens, original-proof bytes, source URLs, actual
caption text, hidden credentials, source media URLs or private evidence notes.
The content view is a separate authenticated POST returning non-executable
plain text; original files use `application/octet-stream` and
`Content-Disposition: attachment`, never inline HTML. Current reviewer
identity and RBAC are derived from the signed server session, not from form
fields or untrusted draft JSON. The original image/video itself is **not**
rendered by this phase; physical-media visual review remains a separate
operational requirement.

## Transport and security constraints

- An exact configured HTTPS origin and host must match. Do not trust raw
  `X-Forwarded-Proto` headers; the trusted TLS terminator must supply the
  correct WSGI scheme and host.
- The **upstream authenticated service**, not this source module, must issue
  a host-only `__Host-sns-review` cookie with `Secure`, `HttpOnly`,
  `SameSite=Strict`, and `Path=/`. The cookie contains a signed RS256 JWT
  verified against server-pinned public keys and a server-owned, revocable
  session record. Neither the cookie nor a signing key is generated here.
- Every application request verifies a fresh MFA-backed session, enabled
  reviewer role and exact account scope. An authenticated GET does not grant
  additional rights.
- Every POST demands the exact same `Origin`, a session-bound HMAC-based
  CSRF value for the action + candidate, strict field allowlists, exact
  content type/length and bounded payload size. Operation IDs are randomized,
  and optimistic version/hash checks reject double submission and stale UI.
- Every response sets no-store/cache protections, a restrictive Content
  Security Policy, no-referrer, no-sniff and frame denial. Styling is static,
  self-hosted CSS; no external fonts/scripts/network dependencies.
- No raw provider/database exception, bearer token, private proof content
  or original post text is placed in errors. Source/inbox errors cannot enable
  new approvals; previously recorded reviews remain revocable.
- Original access checks the latest trusted evidence for the exact review
  candidate, asset and source, then the vault's authenticated, unrevoked and
  unexpired original bytes. Downloading an original is **not proof that a
  human read or understood it**; UI confirmation is an attestation.

The application requires caller-injected `database_factory`,
`verifier_factory`, `canonical_factory`, `inbox`,
`origin`, `trusted_issuer` and a secret CSRF HMAC key with at least 32
bytes. The database factory must provide **one dedicated private SQLite
database connection per request** with foreign keys enabled. The session
authority and evidence vault must use that same connection. No `main()`,
server startup or default credentials are provided.

## Important remaining blockers

- There is no connected real IdP login/cookie provisioning, no deployed
  protected database, no actual canonical backend inbox/queue implementation,
  and no runtime or browser canary. Ephemeral test keys and fake data are
  development evidence only.
- The trusted precommit contract still requires a verified, current
  `READY` queue and final human-review draft, which does not itself
  transition `WAITING_REVIEW` to `READY`. Product readiness needs an
  approved lifecycle design without circumventing current gates.
- SQLite reviewer/event journal and the Google Sheets queue remain
  **non-atomic across stores**. Neither a current match nor a reviewer
  confirmation guarantees that a later publisher observes the same content.
- Existing READY writers, cron, autonomous pipelines and publisher entrypoints
  are not yet switched to one mandatory publication authority. A review record
  remains nonauthoritative until **Phase 5B-6** implements and tests all
  publish-time gates and legacy bypass protections.
- Real IdP key rotation, secret distribution, session-cookie security,
  CSP/browser QA, monitoring, proof-access audit exports, backup/restore and
  signed external audit anchoring still need operational validation.

Every successful mutation response remains:
`effective_approval=false`, `ready_transitions_performed=false`,
`publish_authorized=false`, and
`external_queue_atomicity_guaranteed=false`.
There is no new path that sets production Sheets READY or invokes publishers.

## Developer verification

```bash
python3 scripts/test_media_review_secure_console.py
python3 scripts/test_media_review_verified_adapters.py
python3 scripts/test_media_review_trusted_precommit.py
python3 scripts/test_media_review_transactional_ledger.py
python3 scripts/test_media_review_queue_reconciliation.py
python3 scripts/run_repository_tests.py
python3 scripts/test_all_workflows_safety_flags.py
python3 -m ruff check --select E9,F63,F7,F82 src scripts
python3 -m compileall -q src scripts
git diff --check
```

## Operations handoff — VPS management only, NOT in this development chat

Tool: SNS Growth Engine. Repository:
`dev-ch-hhuk39/sns-growth-engine`.

No immediate deployment or migration is required by this source-only PR.
Before any eventual production setup, provision a nonpublic trusted IdP
and canonical queue/inbox, private SQLite volume, dedicated WSGI service,
TLS/cookie termination, CSRF secret and a tested migration
`0001 -> 0002 -> 0003`. Verify reviewer roles, all account isolation,
original-proof downloads, disabled/revoked sessions, backup and restore,
read/write concurrency, source conflicts, and rollback on disposable data.
The VPS management chat must apply the shared deploy lock and resource
preflight and use only the exact merged commit SHA. Do not deploy this
code as a publicly accessible WSGI app without all dependencies and
dedicated integration/security review.

Next development phase: **5B-6**, an authoritative queue/publisher safety
boundary with 100% legacy READY-writer entrypoint inventory, prepublish
authorization and rights checks, kill switch, and cross-store consistency.
