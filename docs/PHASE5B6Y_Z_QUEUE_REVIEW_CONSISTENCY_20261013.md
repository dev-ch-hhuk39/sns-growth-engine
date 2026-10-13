# Phase 5B-6Y/Z: Immutable queue identities and safe human-review synchronization

Date: 2026-10-13 JST. Mac source-only continuation from local commit 72efac0.

**Not deployed. No production Google Sheets change, network fetch, SNS post,
paid AI, GitHub Actions CI or shared VPS operation is authorized by this code.**

## Problem confirmed from actual repository

- SheetsClient.update_queue_item previously accepted changes to account_id,
  platform, slot_id and draft_id, including outside an explicit approved
  migration. Bulk READY operations could partly write valid rows while another
  target was missing, and the writer could report a count for an unknown field.
- get_queue_item and find_queue_item returned the first matching row even if
  a legacy Sheet contained duplicate queue IDs/draft+platform identities.
- sync_publication_review used the generic Sheets transient-error retry helper
  for append_rows and batch_update. A timeout can occur after a commit, so
  this is an unsafe retry for non-idempotent writes. The script also silently
  treated an unavailable review worksheet as empty and could implicitly
  create/extend tabs during a plan.
- apply_publication_review_decisions turned review and queue arrays into
  dictionaries keyed by queue ID without duplicate detection. It could
  report APPLIED after only verifying that a queue row existed, not that the
  requested review or queue state was saved.
- A review_decision=OK was preserved across updates of public_post_text,
  upstream reference, media identity or account. It could become an approval
  for a *different*, previously unreviewed candidate.

## Implemented Phase 6Y: Queue identity invariants

- Added src/publishers/queue_identity_policy.py. Queue, account, platform,
  slot and draft identifiers cannot be silently rewritten by a patch.
  READY promotion is blocked from posted, rejected, failed, processing and
  uncertain-publish terminal states.
- Real and mock SheetsClient update, read and draft-match lookups use a single
  unambiguous identity or refuse. The bulk path checks all requested IDs,
  writable fields and header uniqueness before a single provider write. Any
  missing target blocks the complete batch, preventing partial approvals
  caused by the initial preflight.
- Existing media READY interlock, public text validators and publisher
  identity/readback checks remain in force.

## Implemented Phase 6Z: Human-review data consistency

- Added scripts/review_board_integrity.py: reject duplicate queue/review
  identities, missing IDs with content, and mismatched account/platform
  binding. The review synchronizer and decision applier both use it.
- sync_publication_review.py no longer creates or extends spreadsheets.
  Read-only plans never mutate Sheets. Missing review worksheets fail closed
  rather than losing stored human review decisions.
- Reads retain bounded 429/5xx retry. Append/update calls are performed
  **once** through the existing sheets_write_once helper with RAW values.
  The synchronizer verifies exact persisted updated fields, not just the
  existence of an ID. Unknown acknowledgements/partial writes require
  independent operator reconciliation.
- apply_publication_review_decisions.py preflights headers and identities
  before mutation, verifies both queue and review row fields after writing,
  never blindly replays an unknown result and uses RAW review-cell updates.
  Cross-tab operations are not atomic; an uncertain outcome must not be
  automatically re-applied or treated as a successful approval.
- The two CLIs now require --use-sheets in addition to their existing
  --apply confirmation, preventing a MOCK_PLAN from being reported as a
  successful real apply.
- publication_review_board.py compares a candidate's public text, source,
  media asset/type, account and route with the **original reviewed view**.
  Existing human decisions and notes are preserved for audit, but if material
  evidence changed, review_status becomes STALE_REVIEW_RECHECK_REQUIRED.
  An old OK/NG/HOLD does not apply to a replaced candidate. To reapprove:
  1) clear the old review_decision;
  2) run a fresh review-board sync;
  3) review the new content and enter the new decision.
  Merely setting OK again without clearing/resyncing cannot bypass the gate.
- Protected media still requires its independent authenticated authority.
  A stale or editable review row never grants media publishing permission.

## Verification

- New offline regression suites: test_queue_identity_transition_policy.py
  and test_publication_review_write_safety.py, including duplicate/cross
  account cases, uncertain ACK, missing readback, stale reviewed text/source,
  signed-off media interlock and explicit CLI permission.
- Existing media-review fixture now persists synthetic batch cell writes so
  post-write verification remains mandatory in tests.
- Focused QA runs existing publication-review, queue writer, media interlock
  and metric safety tests as well as the new adversarial cases.
- Full local repository test evidence and local commit SHA are recorded in
  the top of docs/current-work.md after verification.

## Hard limits / work that is NOT completed

Google Sheets does not provide a compare-and-swap transaction for these
separate methods, and a reviewer can still edit cells concurrently. Preventing
all races requires an operations-owned distributed lock and a *single*
authoritative writer, with a completed migration of the existing legacy
mutation inventory. Do not assume this is an exactly-once distributed queue.

No protected SQLite operational cutover, Google principal/ACL, phishing
resistant staff IdP integration, canary, actual media posting, real
24/72/168-hour observations or same-account measured PDCA evidence is
delivered by these offline guards. The common VPS chat owns real deployment,
backup, migration, rights and operational verification. This repository work
does not request or attempt those actions.

## Final Mac-local QA evidence

- Full offline repository regression: **986/986 test scripts PASS**.
- Workflow static safety, Ruff fatal rules, Python compile, staged/unstaged
  diff checks, local gitleaks scan: **PASS**.
- Source-only synthetic fixtures; neither production Sheets state nor live
  media/post/metric evidence is inferred from these results.
- Local JSON evidence: /tmp/sns-20261013-phase6yz-full.json and companion
  repository_result.json under /tmp/sns-20261013-phase6yz-full-logs/.
  These temporary logs are not committed and not production records.
- No provider login, API upload, GitHub push, PR, merge, Actions execution,
  common VPS mutation or production write occurred.
