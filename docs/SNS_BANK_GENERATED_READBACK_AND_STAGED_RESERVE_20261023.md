# SNS Growth Engine evergreen generated-READY incident resolution

Date: 2026-10-23 JST
Target: SNS Growth Engine only; no changes to Cloudflare R2, other VPS
applications, external publication permissions or paid provider budgets.

## Evidence (production, READ ONLY)
The posting-disabled Beauty 24h workflow #39941995241 checked live
delivery 1/1 PASS but the bank step stopped with fixed private hint
EVERGREEN_APPROVAL_READ_AFTER_WRITE_FAILED. That code previously combined
four independent failures (row absent/duplicate, wrong slot, incomplete
READY approvals and the runtime no-post gate) into one RuntimeError.

A separate four-tab Google Sheets read-only snapshot identified nine
READY rows dated seven days into the future in the Beauty 11:30 slot,
all passing three basic approval flags and later the full public-text,
hybrid source evidence and no-post process_one dry-run gate.
Of those, six had the explicit _reserve_1/_reserve_2 queue identity emitted
by prepare_beauty_review_candidates.py. All six had unique queue IDs,
were not in the bank or posted-results tabs, and were not referenced by
the current content-slot-run queue ID field. All six also passed the
actual runtime guard when their two temporary date fields were cleared
in memory, without writing data.

These facts demonstrate that already approved recoverable reserve
candidates exist, but do not establish which newly created ID caused
the historical failure (the private stdout/ID was deliberately not logged).

## Code repair
1. Validate the generated queue readback as a bounded all-or-nothing
   batch (max three IDs). Categorize missing/duplicate IDs, immutable
   slot/account conflicts, not-READY, incomplete approvals and runtime
   check failures with fixed aggregate counts. Never expose queue IDs or
   unpublished text in public CI reports.
2. Malformed or unverified readback never admits a candidate. Stop further
   paid attempts immediately if the persisted identity or approval is
   ambiguous; only pure runtime/editorial rejection may use the already
   existing at-most-ten-theme budget.
3. If a generator reports READY_REPLENISHED without returned IDs,
   treat it as an unverified readback and stop, not as a success.
4. Before any new paid request, additionally discover the distinct
   Beauty _reserve_1/_reserve_2 artifacts previously generated for the
   immutable beauty_1130 slot. Require the exact queue ID pattern,
   expected generator, READY status, same date encoded in its ID and
   business_date field, T+2 to T+7 days, no conflicting schedule date,
   unique queue ID, no posted/bank/slot-run use, and all unchanged
   regular owner/editorial/runtime gates. A primary candidate (without
   _reserve_) is never moved, even if it shares the same future slot.
5. Reuse only the existing verified_bank_admission batch transaction,
   which clears temporary dates while preserving slot identity,
   appends bank evidence and verifies the canonical queue + bank
   read-after-write. A failed receipt never increases usable inventory.

## Explicit non-goals and operational acceptance
- No real Threads publishing or cross-app writes; P0/post switches OFF.
- No quality/review bypass, unknown-ID adoption, cross-slot migration,
  content rewrites, real paid budget increase, new API scheduling, or R2
  backup changes.
- Success requires actual persisted 30/30/30 approved current-slot
  reserves and repeated 3-account scheduled READY/bank PASS, not a
  synthetic PASS or a 24h delivery-read-only 7/7 snapshot.
- The unresolved Google Sheets native full restore limitation tracked
  in #437 and authorized actual-post/metrics evidence are independent
  acceptance blockers. A single passing batch does not close #441.
