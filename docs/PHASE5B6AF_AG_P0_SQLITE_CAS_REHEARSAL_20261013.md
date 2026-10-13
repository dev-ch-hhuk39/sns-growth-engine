# Phase 5B-6AF/AG - P0 SQLite one-use CAS and offline rehearsal

Date: 2026-10-13 JST. Local source work from commit 6d9cc69.
NO real Sheets writes, SNS posting, operational DB promotion or VPS deployment.

## Confirmed state before this phase

- Google Sheets is still the operational queue and posted-results source.
- The protected SQLite media review/shadow/managed/outbox journal is separate,
  and its blocked reservation is not an authenticated live posting permit.
- P0 publisher cannot atomically lock an external Google Sheet and complete a
  Threads API call. Row ID uniqueness and readback reduce but do not remove
  concurrent-writer races. Unknown outcomes must not be automatically reposted.

## Implemented offline P0 rehearsal

- New migration 0014 creates separate sns_p0_rehearsal_heads/events tables
  using foreign keys, globally unique queue_id, immutable journal events,
  unique operation IDs and revisioned SQLite head compare-and-swap.
- New p0_queue_cas_rehearsal.py provides OBSERVE, CLAIM, UNCERTAIN and
  CANCEL before a claim. Its ONLY states end in _BLOCKED. It does not expose
  a publish capability and explicitly refuses authorize_external_post().
- BEGIN IMMEDIATE serializes competing SQLite writers and compares exact
  revision, prior event hash, account, platform and source digest. A claim
  can occur at most once, even if another process races for the same queue.
  Expiration cannot resurrect a claimed or outcome-unknown candidate.
- Each commit appends a canonical SHA-256-chained event, validates full
  event/head history and returns only a hashed identity and fixed boolean
  denials. Lost SQLite acknowledgement and mismatched readback are not
  treated as permission to retry.
- Validation allows only the two currently scoped synthetic P0 accounts
  (night_scout and liver_manager), Threads only, strict queue/operation IDs,
  fresh observed timestamps and 64-character SHA-256 input.
- This is intentionally NOT an operational queue import. The supplied
  source digest is NOT authenticated evidence from Google Sheets and no
  actual provider precommit source read happens here.
- New rehearse_p0_queue_cas.py --demo creates a fresh TEMPORARY SQLite
  database, runs synthetic observe->claim->unknown, verifies replay denial,
  and returns CUTOVER_BLOCKED with exit code 2. There is no --apply option.
  Optional report output must be an absolute path outside the repository,
  is owner-only permission mode 0600 and cannot overwrite any existing file.
- The demo also rechecks the already frozen 6H static AST Sheets writer
  inventory and reports remaining P0/all mutation counts as NOT MIGRATED.
  A passing local SQLite CAS is NEVER treated as 71 P0 live writers migrated.

## Offline tests

- scripts/test_p0_queue_cas_rehearsal.py covers 16 adversarial/success
  tests: concurrent separate SQLite connections, stale CAS, lost-ACK state,
  duplicate operation ID/queue ID, account crossing, input/clock scope,
  terminal replay, immutable events, head tamper, injected rollback and
  blocked authorization.
- Mac focused QA includes this new suite. The existing 6H inventory,
  protected media, source/rights, reporting, publishing, metrics and
  failure-state tests remain unchanged.
- Example test-only command:
  python3 scripts/rehearse_p0_queue_cas.py --demo
- Expected exit code is 2, with status CUTOVER_BLOCKED, even when the
  synthetic CAS demonstration passes and blocks duplicates.

## Actual migration still required - NOT delivered by these changes

1. Ops/Owner establish one authorized queue writer, scoped provider identity,
   backup/restore and a source snapshot with trustworthy provenance.
2. Inventory external/cron/mounted writer processes. Stop or serialize all
   legacy mutation paths. The 6H inventory only covers direct Python AST
   mutations; it is not exhaustive production discovery.
3. Migrate the real P0 queue and posted-results writer families with
   verified source/target parity and atomic exclusive authority over the
   actual publishing sink, not merely over a local rehearsal DB.
4. Revalidate content/media rights at the last pre-publish boundary and
   reconcile ambiguous API outcomes without auto-retry or false POSTED.
5. Approved live canaries, fresh provider readbacks and real 24/72/168-hour
   measured feedback are required before calling production ready.

The existing media publish safety stop, disabled X outbound scope, separated
VPS-operations ownership and no-GitHub-Actions policy remain unchanged.

## Full local QA record

- Full offline repository: 989/989 PASS, no test-script failures.
- Focused gate, workflow static, Ruff fatal checks, compile, clean staged/unstaged diff and gitleaks: PASS.
- Evidence in /tmp/sns-20261013-phase6afag-full.json and related log directory on Mac only.
- No provider-connected canary, source-of-truth cutover or authorization is claimed.
