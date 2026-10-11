# Phase 5B-4A: Trusted reviewer precommit policy

## Intent and delivered behavior

Implements an independent, importable server-side policy core for verifying
a proposed Phase 5B-2 media approval **before a future canonical commit**.
This **does not authenticate users itself**; a trusted session verifier and
canonical reader must be supplied by a separately secured service.

The policy can confirm that the trusted adapters returned a verified reviewer,
current READY media queue record, intact plan/receipt hashes, and fresh original
source/evidence records. It deliberately returns:

- `status=PRECOMMIT_CHECKS_PASSED_NO_APPROVAL`
- `requires_atomic_approval_commit=true`
- `requires_publish_time_revalidation=true`
- `effective_approval=false`
- `ready_transitions_performed=false`
- `writes_performed=false`
- `publish_authorized=false`

The code has no HTTP endpoint, database writer, credential source or publisher.
It **cannot** approve or publish independently. Importing the module into a
public API without a cryptographically verified identity adapter and an
access-controlled canonical data reader is expressly forbidden.

## Integration contract

`scripts/media_review_trusted_precommit.py` exposes:

- `SessionVerifier.verify(bearer_token, now)` — the implementer MUST verify
  token signature, algorithm allowlist, issuer, audience, revocation,
  session binding and MFA server-side, without trusting request JSON.
- `CanonicalReviewReader.load_current(account_id, slot_id, queue_id)` —
  implement with the authoritative queue, evidence store and review ledger,
  enforce account RBAC and return one consistent snapshot from trusted storage.
- `ReviewRequest` — exact account, media slot, queue ID, expected queue
  revision, complete plan fingerprint, draft chain head and draft event hash,
  plus explicit human acknowledgement.
- `evaluate_precommit` — pure verification only, requiring the two providers
  and a pinned trusted identity issuer configured server-side.

No adapter is supplied by this PR. If providers are absent, token verification
fails, queue version differs, or stored evidence is incomplete, the request
is **blocked**, without leaking tokens or original evidence in error messages.

## Required checks

1. Only MEDIA_REVIEWER or ADMIN with explicit *matching account scope*;
   the authenticated subject MUST match the reviewer ID on the most recent
   approved draft event for the exact candidate. Recent MFA and an unexpired
   session are required.
2. Exact managed account + slot + queue ID; SHA-256 hash binding to the
   Phase 5B-1 plan, untampered Phase 5B-2 receipt chain and expected event.
3. Fresh canonical queue revision and `READY` status, Threads platform,
   valid current rights and permission flags, no rights review hold,
   media asset/source lineage and all existing media quality checks PASS.
4. The complete referenced evidence set must be present in a trusted
   evidence repository; each proof must match account, slot, queue, asset,
   source and organic Threads usage, allow Japanese territory, have a
   recently verified original reference, and be neither revoked nor expired.
5. Passing the checks only generates a bounded precommit report. It never
   commits anything to Sheets or grants authority to another process.

## Important lifecycle distinction

The existing Phase 5B-1 plan examines queue rows already marked READY.
Therefore Phase 5B-4A is a **review approval eligibility check for already
READY candidates**, not a WAITING_REVIEW-to-READY transition. Earlier Sheets
review paths such as `approve_queue.py` and
`apply_publication_review_decisions.py` remain untouched; they are not
automatically secured by this policy and require a separate review before
being connected to the new workflow.

## Remaining implementation (Phase 5B-4B and onwards)

- Choose and connect a real internal authentication provider and account
  role-scoping policy; test token signature, audience, revocation and expiry.
- Deploy a protected original rights/evidence repository and authoritative
  reviewer-event ledger (not a JSON file or user-modifiable Google Sheet).
- Define transactional compare-and-swap on queue revision + review head;
  append the authenticated approval/revocation atomically and idempotently.
- Add publisher-side rights/revocation revalidation immediately before
  dispatch, keeping existing global publishing controls off until explicitly
  approved. The approval itself must not start a post.
- Security-review legacy Sheets review/READY write paths for bypasses.
- Only after these independent security checks pass, connect the UI with
  server-side authentication and allow recording authoritative decisions.

**All shared VPS operations, DB migrations and production deploys must be
handed off to the dedicated shared VPS management chat.** This phase
does not perform them.

## Tests

`python3 scripts/test_media_review_trusted_precommit.py`

The tests inject explicit FAKE signed-session/evidence providers only in
memory; no real login, OAuth flow, DB or publisher is invoked.

Full GitHub CI is required before merge. Never interpret offline test PASS
as proof that external identity and evidence providers are configured.
