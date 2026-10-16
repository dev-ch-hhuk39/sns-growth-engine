# Phase 5B-6AC/AD/AE — P0 Publisher Identity and Durable Post Finalization

Date: 2026-10-13 JST. Local source-only continuation from commit a8bb88d.
Not merged, not deployed, no real posting or production Google Sheets write.

## Reviewed and corrected risks

1. The Threads queue selector previously filtered to one account before it
   could detect duplicate global queue IDs. A collision between Night and
   Liver could lead to ambiguous operational target selection.
2. Draft/social derivative lookup used first-match or last-match semantics,
   allowing account mixing when source IDs were reused. A full global ban on
   reusable draft IDs is also incorrect: explicitly owner-scoped same IDs
   must coexist. We now accept an unambiguous exact-account row and only
   accept a legacy ownerless row when it is the only possible match.
3. Pre-publish PROCESSING confirmation previously checked the queue text and
   account but not the media asset, source IDs, route and slot. Those fields
   now must match the originally approved selected row at readback.
4. The publisher could return POSTED despite failure to write final
   queue.status=POSTED. It now returns POSTED_SAVE_UNVERIFIED and stops
   metrics/PDCA finalization on missing or uncertain acknowledgement.
5. The publisher transport can return success with no stable external post
   ID or permalink. That is now PUBLISH_OUTCOME_UNVERIFIED; never fabricate a
   POSTED record, schedule metrics or automatically retry the remote post.
6. The posted-result validator used the first matching result_id and could
   accept duplicate result, queue or provider post IDs. It now checks global
   uniqueness, explicit account and status, and repeats that verification
   on the second post-write readback.
7. Legacy Sheets headers were cached by id(worksheet) even across object
   reuse and schema drift. Each mutation now requests fresh headers and
   refuses duplicate columns or missing submitted queue/result fields.
   It also refuses terminal-state rollback and requires PROCESSING before
   a queue can become POSTED.
8. CLI --dry-run now creates SheetsClient(dry_run=True), making the client
   itself write-disabled rather than relying only on branch checks.

## Verification

- New synthetic adversarial suite:
  scripts/test_threads_publisher_identity_finalization.py
- Expanded direct persistence contract tests:
  scripts/test_publisher_delivery_contract.py
- Existing regression suites for pre-publish locks, legacy Sheets safety,
  media dry-run, duplicate guard, and Beauty account scope were also included
  in the Mac focused quality gate.
- Existing frozen legacy AST mutation inventory remains active and unchanged.
  This phase removes no real legacy writer and does not grant any.
- All code is off-network. Provider calls in tests are patched in memory.
  Failure reason codes contain no raw candidate body or credentials.

## Important remaining limitations and Ops requirements

Sheets is still the operational source of truth. Its row writes are not
transactional compare-and-swap, even with unique-ID preflight and readback.
A concurrent external writer can change values between those steps.
True one-use posting authority, exclusive writer ownership and committed
SQLite migration are NOT implemented by these changes.

A confirmed remote post with incomplete local persistence must be reconciled
by Ops using the actual provider post ID/URL and the real authoritative Sheet
before deciding further actions. No automatic repost, deletion, rollback of
the external post, or blind queue state rewrite is safe.

Remaining acceptance: separate service identity and scoped ACL, host-wide
one-use lock, exact publisher and posted-results cutover ownership, backup
and restore tests, verified real provider canary, rights checks immediately
before media post, and real 24h/72h/168h observations and attribution.
The common VPS/Ops chat owns production changes. No GitHub Actions or Codex
needed for the Mac-local testing in this phase.

## QA commands

    python3 scripts/run_local_quality_gate.py --mode focused
    python3 scripts/run_local_quality_gate.py --mode full

A full offline run is NOT signed operational evidence or live permission.

## Final Mac-local QA evidence — 2026-10-13 JST

- New synthetic/adversarial publisher isolation/finalization suite: 16/16
  unittest cases PASS. Sheets 429/409 freshness suite: 17/17 PASS.
- Full repository offline regression after changes: **988/988 test scripts
  PASS**, 0 failed. Static workflow safety, Ruff, Python compile, Git
  staged/unstaged diff checks and local gitleaks scan: PASS.
- First full regression showed a single historical static test asserting
  that an unsafe worksheet-id header cache must exist (987/988). Updated
  the test to assert fresh headers and no cache, without weakening the
  runtime safety condition. The final complete rerun passed 988/988.
- Local evidence report:
  /tmp/sns-20261013-6ac-ae-full-final.json
  and companion repository_result.json under
  /tmp/sns-20261013-6ac-ae-full-final-logs/.
- Excluded external credential/API probes are still NOT production proof.
  No X/Threads publication, paid API call, Sheets write, SQLite authority
  promotion, GitHub Actions run, public push or common VPS change occurred.
